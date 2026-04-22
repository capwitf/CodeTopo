from __future__ import annotations

import hashlib
import warnings
from dataclasses import dataclass, field
from pathlib import Path

try:
    from tree_sitter import Language, Parser

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False
    warnings.warn("tree-sitter is not installed.")


@dataclass
class SymbolDef:
    name: str
    kind: str
    file_path: str
    start_line: int
    end_line: int
    signature: str
    docstring: str | None = None
    parent_class: str | None = None
    checksum: str = ""

    @property
    def qualified_name(self) -> str:
        return f"{self.parent_class}.{self.name}" if self.parent_class else self.name


@dataclass
class CallEdge:
    caller_file: str
    caller_name: str
    callee_name: str
    call_line: int
    resolved_file: str | None = None
    resolved_def: SymbolDef | None = None

    @property
    def is_cross_file(self) -> bool:
        return self.resolved_file is not None and self.resolved_file != self.caller_file


class ImportDecl(str):
    def __new__(cls, module: str, name: str | None = None, alias: str | None = None):
        value = module
        if name:
            value += f".{name}"
        if alias:
            value += f" as {alias}"
        return super().__new__(cls, value)

    def __init__(self, module: str, name: str | None = None, alias: str | None = None):
        self.module = module
        self.name = name
        self.alias = alias

    @property
    def is_wildcard(self) -> bool:
        return self.name == "*"


@dataclass
class ParseResult:
    file_path: str
    language: str
    symbols: list[SymbolDef] = field(default_factory=list)
    call_sites: list[CallEdge] = field(default_factory=list)
    imports: list[ImportDecl] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class BaseParser:
    language_name: str = ""

    def __init__(self) -> None:
        if not TREE_SITTER_AVAILABLE:
            raise RuntimeError("tree-sitter is not installed.")
        self._lang: Language = self._build_language()
        self._parser = Parser(self._lang)

    def _build_language(self):
        raise NotImplementedError

    def _extract_symbols(self, root, source: bytes, file_path: str) -> list[SymbolDef]:
        return []

    def _extract_calls(self, root, source: bytes, file_path: str) -> list[CallEdge]:
        return []

    def _extract_imports(self, root, source: bytes) -> list[ImportDecl]:
        return []

    def parse_file(self, file_path: str | Path) -> ParseResult:
        path = Path(file_path)
        result = ParseResult(file_path=str(path), language=self.language_name)
        try:
            source = path.read_bytes()
            tree = self._parser.parse(source)
            result.symbols = self._extract_symbols(tree.root_node, source, str(path))
            result.call_sites = self._extract_calls(tree.root_node, source, str(path))
            result.imports = self._extract_imports(tree.root_node, source)
            checksum = hashlib.md5(source).hexdigest()
            for symbol in result.symbols:
                symbol.checksum = checksum
        except Exception as exc:
            result.errors.append(f"Parse error: {type(exc).__name__}: {exc}")
        return result

    def parse_source(self, source: str, file_path: str = "<string>") -> ParseResult:
        result = ParseResult(file_path=file_path, language=self.language_name)
        try:
            encoded_source = source.encode("utf-8")
            tree = self._parser.parse(encoded_source)
            result.symbols = self._extract_symbols(tree.root_node, encoded_source, file_path)
            result.call_sites = self._extract_calls(tree.root_node, encoded_source, file_path)
            result.imports = self._extract_imports(tree.root_node, encoded_source)
        except Exception as exc:
            result.errors.append(f"Parse error: {type(exc).__name__}: {exc}")
        return result

    @staticmethod
    def _node_text(node, source: bytes) -> str:
        return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    @staticmethod
    def _captures_to_dict(captures) -> dict[str, list]:
        if isinstance(captures, dict):
            return captures
        result: dict[str, list] = {}
        for node, name in captures:
            result.setdefault(name, []).append(node)
        return result

    def _run_query(self, pattern: str, root) -> dict[str, list]:
        try:
            try:
                from tree_sitter import Query

                query = Query(self._lang, pattern)
            except ImportError:
                return self._captures_to_dict(self._lang.query(pattern).captures(root))

            try:
                from tree_sitter import QueryCursor

                return self._captures_to_dict(QueryCursor(query).captures(root))
            except ImportError:
                return self._captures_to_dict(query.captures(root))
        except Exception:
            return {}
