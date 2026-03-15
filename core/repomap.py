from __future__ import annotations

import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from base_parser import SymbolDef
from call_resolver import CallGraph, ResolvedCall
from language_support import EXTENSION_TO_LANGUAGE

try:
    import networkx as nx

    NETWORKX_AVAILABLE = True
except ImportError:
    NETWORKX_AVAILABLE = False


@dataclass
class RepomapEntry:
    file_path: str
    language: str
    symbols: list[SymbolDef]
    outgoing_calls: list[ResolvedCall]
    incoming_calls: list[ResolvedCall]


@dataclass
class Repomap:
    project_root: str
    entries: dict[str, RepomapEntry] = field(default_factory=dict)
    call_graph: CallGraph | None = None

    def stats(self) -> dict[str, object]:
        total_symbols = sum(len(entry.symbols) for entry in self.entries.values())
        cross_file_edges = self.call_graph.cross_file_edges if self.call_graph else []
        return {
            "files": len(self.entries),
            "symbols": total_symbols,
            "cross_file_calls": len(cross_file_edges),
            **(self.call_graph.stats() if self.call_graph else {}),
        }

    def to_text_skeleton(
        self,
        max_tokens_hint: int = 4000,
        include_docstring: bool = True,
        only_cross_file: bool = False,
    ) -> str:
        lines: list[str] = []
        char_budget = max_tokens_hint * 3

        for file_path, entry in sorted(self.entries.items()):
            rel_path = self._relative(file_path)
            class_methods: dict[str | None, list[SymbolDef]] = defaultdict(list)
            for symbol in entry.symbols:
                class_methods[symbol.parent_class].append(symbol)

            if only_cross_file:
                involved = (
                    {call.edge.caller_name for call in entry.outgoing_calls if call.is_cross_file}
                    | {
                        call.callee_def.qualified_name
                        for call in entry.incoming_calls
                        if call.callee_def is not None
                    }
                )
                if not involved:
                    continue

            lines.append(f"\n{'=' * 4} {rel_path} {'=' * max(0, 48 - len(rel_path))}")

            for parent_class, symbols in class_methods.items():
                if parent_class:
                    lines.append(f"  class {parent_class}")
                    indent = "    "
                else:
                    indent = "  "

                for symbol in symbols:
                    if symbol.kind == "class":
                        continue

                    lines.append(f"{indent}{symbol.signature}")
                    if include_docstring and symbol.docstring:
                        lines.append(f"{indent}  # {symbol.docstring.splitlines()[0][:80]}")

                    for call in entry.outgoing_calls:
                        if (
                            call.is_cross_file
                            and call.edge.caller_name in (symbol.name, symbol.qualified_name)
                            and call.callee_def is not None
                        ):
                            target = self._relative(call.callee_def.file_path)
                            lines.append(
                                f"{indent}  -> {call.edge.callee_name} "
                                f"[{target}:{call.callee_def.start_line}]"
                            )

            if sum(len(line) for line in lines) > char_budget:
                lines.append("\n  ... (truncated) ...")
                break

        return "\n".join(lines)

    def to_networkx(self):
        if not NETWORKX_AVAILABLE:
            raise RuntimeError("networkx is not installed. Run `pip install networkx`.")
        if self.call_graph is None:
            raise ValueError("call_graph is not initialized")

        graph = nx.DiGraph()
        for node_key, symbol in self.call_graph.nodes.items():
            graph.add_node(
                node_key,
                label=symbol.qualified_name,
                kind=symbol.kind,
                file=symbol.file_path,
                signature=symbol.signature,
                line=symbol.start_line,
                docstring=symbol.docstring or "",
            )

        for call in self.call_graph.resolved_edges:
            if call.callee_def is None:
                continue
            source = f"{call.edge.caller_file}::{call.edge.caller_name}"
            target = f"{call.callee_def.file_path}::{call.callee_def.qualified_name}"
            if source in graph.nodes and target in graph.nodes:
                graph.add_edge(
                    source,
                    target,
                    call_line=call.edge.call_line,
                    is_cross_file=call.is_cross_file,
                )
        return graph

    def to_json(self, indent: int = 2) -> str:
        if self.call_graph is None:
            return json.dumps({"nodes": [], "links": []}, ensure_ascii=False)

        nodes = [
            {
                "id": key,
                "label": symbol.qualified_name,
                "kind": symbol.kind,
                "file": self._relative(symbol.file_path),
                "signature": symbol.signature,
                "line": symbol.start_line,
                "docstring": symbol.docstring or "",
            }
            for key, symbol in self.call_graph.nodes.items()
        ]

        links: list[dict[str, object]] = []
        seen: set[tuple[str, str]] = set()
        for call in self.call_graph.resolved_edges:
            if call.callee_def is None:
                continue

            source = f"{call.edge.caller_file}::{call.edge.caller_name}"
            target = f"{call.callee_def.file_path}::{call.callee_def.qualified_name}"
            if (source, target) in seen:
                continue

            seen.add((source, target))
            links.append(
                {
                    "source": source,
                    "target": target,
                    "call_line": call.edge.call_line,
                    "is_cross_file": call.is_cross_file,
                }
            )

        return json.dumps({"nodes": nodes, "links": links}, ensure_ascii=False, indent=indent)

    def _relative(self, file_path: str) -> str:
        try:
            return str(Path(file_path).relative_to(self.project_root))
        except ValueError:
            return file_path


class RepomapBuilder:
    SUPPORTED_EXTENSIONS = EXTENSION_TO_LANGUAGE.copy()

    def __init__(
        self,
        project_root: str,
        exclude_patterns: list[str] | None = None,
        verbose: bool = False,
    ) -> None:
        self.project_root = project_root
        self.exclude_patterns = exclude_patterns or [
            "*/test*",
            "*/vendor/*",
            "*/.git/*",
            "*/node_modules/*",
            "*/__pycache__/*",
            "*/build/*",
            "*/dist/*",
            "*/.venv/*",
            "*/venv/*",
        ]
        self.verbose = verbose

    def build(self) -> Repomap:
        self._ensure_language_path()
        files = self._scan_files()
        parser_map = self._build_parser_map({language for _, language in files})

        from call_resolver import CallResolver

        parse_results = []
        for file_path, language in files:
            parse_result = parser_map[language].parse_file(file_path)
            parse_results.append(parse_result)

        resolver = CallResolver(parse_results, project_root=self.project_root, verbose=self.verbose)
        call_graph = resolver.resolve()

        repomap = Repomap(project_root=self.project_root, call_graph=call_graph)
        outgoing: dict[str, list[ResolvedCall]] = defaultdict(list)
        incoming: dict[str, list[ResolvedCall]] = defaultdict(list)
        for call in call_graph.edges:
            outgoing[call.edge.caller_file].append(call)
            if call.callee_def is not None:
                incoming[call.callee_def.file_path].append(call)

        language_map = {file_path: language for file_path, language in files}
        for parse_result in parse_results:
            repomap.entries[parse_result.file_path] = RepomapEntry(
                file_path=parse_result.file_path,
                language=language_map.get(parse_result.file_path, parse_result.language),
                symbols=parse_result.symbols,
                outgoing_calls=outgoing.get(parse_result.file_path, []),
                incoming_calls=incoming.get(parse_result.file_path, []),
            )

        return repomap

    def _ensure_language_path(self) -> None:
        language_dir = Path(__file__).parent.parent / "languages"
        if language_dir.exists() and str(language_dir) not in sys.path:
            sys.path.insert(0, str(language_dir))

    def _scan_files(self) -> list[tuple[str, str]]:
        import fnmatch

        root = Path(self.project_root)
        result: list[tuple[str, str]] = []
        for extension, language in self.SUPPORTED_EXTENSIONS.items():
            for path in root.rglob(f"*{extension}"):
                path_str = str(path)
                if not any(fnmatch.fnmatch(path_str, pattern) for pattern in self.exclude_patterns):
                    result.append((path_str, language))
        return result

    def _build_parser_map(self, languages: set[str]) -> dict[str, object]:
        parser_map: dict[str, object] = {}

        if "python" in languages:
            from python_parser import PythonParser

            parser_map["python"] = PythonParser()
        if "java" in languages:
            from java_parser import JavaParser

            parser_map["java"] = JavaParser()
        if "go" in languages:
            from go_parser import GoParser

            parser_map["go"] = GoParser()
        if "c" in languages:
            from c_parser import CParser

            parser_map["c"] = CParser()

        return parser_map
