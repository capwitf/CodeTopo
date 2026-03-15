from __future__ import annotations

import re
from typing import Optional

try:
    import tree_sitter_c as tsc
    from tree_sitter import Language
except ImportError:
    tsc = None

from base_parser import BaseParser, CallEdge, ImportDecl, SymbolDef


class CParser(BaseParser):
    language_name = "c"

    def _build_language(self):
        if tsc is None:
            raise RuntimeError("tree-sitter-c is not installed")
        return Language(tsc.language())

    _CALL_QUERY = """
    (call_expression
      function: [
        (identifier) @call.func
        (field_expression) @call.func
      ]
    ) @call.site
    """

    def _extract_symbols(self, root, source: bytes, file_path: str) -> list[SymbolDef]:
        symbols: list[SymbolDef] = []
        self._walk_definitions(root, source, file_path, symbols)
        return symbols

    def _walk_definitions(self, node, source: bytes, file_path: str, symbols: list[SymbolDef]) -> None:
        if node.type == "function_definition":
            symbol = self._parse_function(node, source, file_path)
            if symbol is not None:
                symbols.append(symbol)
        elif node.type in {"struct_specifier", "union_specifier", "enum_specifier"}:
            symbol = self._parse_type(node, source, file_path)
            if symbol is not None:
                symbols.append(symbol)

        for child in node.children:
            self._walk_definitions(child, source, file_path, symbols)

    def _parse_function(self, node, source: bytes, file_path: str) -> Optional[SymbolDef]:
        declarator = node.child_by_field_name("declarator")
        if declarator is None:
            return None

        name = self._extract_declarator_name(declarator, source)
        if not name:
            return None

        type_node = node.child_by_field_name("type")
        type_text = self._node_text(type_node, source).strip() if type_node else ""
        signature = " ".join(
            part for part in (type_text, self._node_text(declarator, source).strip()) if part
        )

        return SymbolDef(
            name=name,
            kind="function",
            file_path=file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=signature or name,
            docstring=self._get_leading_comment(node, source),
        )

    def _parse_type(self, node, source: bytes, file_path: str) -> Optional[SymbolDef]:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return None

        kind_map = {
            "struct_specifier": "struct",
            "union_specifier": "union",
            "enum_specifier": "enum",
        }
        name = self._node_text(name_node, source)
        kind = kind_map[node.type]
        return SymbolDef(
            name=name,
            kind="class",
            file_path=file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=f"{kind} {name}",
            docstring=self._get_leading_comment(node, source),
        )

    def _extract_calls(self, root, source: bytes, file_path: str) -> list[CallEdge]:
        edges: list[CallEdge] = []
        func_ranges = self._build_function_ranges(root, source)
        captures = self._run_query(self._CALL_QUERY, root)

        for call_node in captures.get("call.site", []):
            call_line = call_node.start_point[0] + 1
            caller_name = self._find_enclosing_function(call_line, func_ranges)
            func_node = call_node.child_by_field_name("function")
            if func_node is None:
                continue

            callee_name = self._node_text(func_node, source).strip()
            if not callee_name or callee_name in _C_CONTROL_LIKE_NAMES:
                continue

            edges.append(
                CallEdge(
                    caller_file=file_path,
                    caller_name=caller_name or "<translation_unit>",
                    callee_name=callee_name,
                    call_line=call_line,
                )
            )

        return edges

    def _build_function_ranges(self, root, source: bytes) -> list[tuple[int, int, str]]:
        ranges: list[tuple[int, int, str]] = []
        self._collect_function_ranges(root, source, ranges)
        return sorted(ranges, key=lambda item: item[0])

    def _collect_function_ranges(self, node, source: bytes, ranges: list[tuple[int, int, str]]) -> None:
        if node.type == "function_definition":
            declarator = node.child_by_field_name("declarator")
            if declarator is not None:
                name = self._extract_declarator_name(declarator, source)
                if name:
                    ranges.append((node.start_point[0] + 1, node.end_point[0] + 1, name))

        for child in node.children:
            self._collect_function_ranges(child, source, ranges)

    @staticmethod
    def _find_enclosing_function(line: int, func_ranges: list[tuple[int, int, str]]) -> Optional[str]:
        best_name = None
        best_size = float("inf")
        for start, end, name in func_ranges:
            if start <= line <= end and (end - start) < best_size:
                best_name = name
                best_size = end - start
        return best_name

    def _extract_imports(self, root, source: bytes) -> list[ImportDecl]:
        text = source.decode("utf-8", errors="replace")
        imports: list[ImportDecl] = []
        for match in re.finditer(r'^\s*#\s*include\s*([<"][^>"]+[>"])', text, re.MULTILINE):
            raw_path = match.group(1).strip("<>\"")
            imports.append(ImportDecl(module=raw_path))
        return imports

    def _extract_declarator_name(self, node, source: bytes) -> Optional[str]:
        if node.type in {"identifier", "field_identifier", "type_identifier"}:
            return self._node_text(node, source)

        inner = node.child_by_field_name("declarator")
        if inner is not None:
            name = self._extract_declarator_name(inner, source)
            if name:
                return name

        for child in node.children:
            name = self._extract_declarator_name(child, source)
            if name:
                return name
        return None

    @staticmethod
    def _get_leading_comment(node, source: bytes) -> Optional[str]:
        source_text = source.decode("utf-8", errors="replace")
        lines = source_text.splitlines()
        start_index = node.start_point[0] - 1
        if start_index < 0:
            return None

        collected: list[str] = []
        in_block_comment = False

        while start_index >= 0:
            raw = lines[start_index].strip()
            if not raw:
                if collected:
                    break
                start_index -= 1
                continue

            if in_block_comment:
                cleaned = raw.lstrip("/*").rstrip("*/").strip("* ").strip()
                if cleaned:
                    collected.insert(0, cleaned)
                if "/*" in raw:
                    break
                start_index -= 1
                continue

            if raw.startswith("//"):
                collected.insert(0, raw[2:].strip())
                start_index -= 1
                continue

            if raw.endswith("*/"):
                in_block_comment = True
                cleaned = raw.rstrip("*/").strip("* ").strip()
                if cleaned:
                    collected.insert(0, cleaned)
                if "/*" in raw:
                    break
                start_index -= 1
                continue

            break

        return " ".join(part for part in collected if part) or None


_C_CONTROL_LIKE_NAMES = frozenset({"if", "for", "while", "switch", "return"})
