from __future__ import annotations

import re
from typing import Optional

try:
    import tree_sitter_go as tsgo
    from tree_sitter import Language
except ImportError:
    tsgo = None

from base_parser import BaseParser, CallEdge, ImportDecl, SymbolDef


class GoParser(BaseParser):
    language_name = "go"

    def _build_language(self):
        if tsgo is None:
            raise RuntimeError("tree-sitter-go is not installed")
        return Language(tsgo.language())

    _FUNC_QUERY = """
    [
      (function_declaration name: (_) @func.name) @func.def
      (method_declaration name: (_) @func.name) @func.def
    ]
    """

    _TYPE_QUERY = """
    (type_declaration (type_spec name: (_) @type.name)) @type.def
    """

    def _extract_symbols(self, root, source: bytes, file_path: str) -> list[SymbolDef]:
        symbols: list[SymbolDef] = []
        func_captures = self._run_query(self._FUNC_QUERY, root)
        for node in func_captures.get("func.def", []):
            name_node = node.child_by_field_name("name")
            if name_node is None:
                continue
            name = self._node_text(name_node, source)
            receiver_node = node.child_by_field_name("receiver")
            receiver_type = self._get_receiver_type(node, source) if receiver_node else None
            kind = "method" if receiver_type else "function"
            symbols.append(
                SymbolDef(
                    name=name,
                    kind=kind,
                    file_path=file_path,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    signature=self._build_func_signature(node, source),
                    docstring=self._get_go_comment(node, source),
                    parent_class=receiver_type,
                )
            )

        type_captures = self._run_query(self._TYPE_QUERY, root)
        for node in type_captures.get("type.def", []):
            name = self._extract_type_name(node, source)
            if not name:
                continue
            kind_str = self._get_type_kind(node, source)
            symbols.append(
                SymbolDef(
                    name=name,
                    kind="class",
                    file_path=file_path,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    signature=f"type {name} {kind_str}",
                    docstring=self._get_go_comment(node, source),
                )
            )
        return symbols

    def _extract_type_name(self, type_decl_node, source: bytes) -> Optional[str]:
        for child in type_decl_node.children:
            if child.type == "type_spec":
                name_node = child.child_by_field_name("name")
                if name_node is not None:
                    return self._node_text(name_node, source)
        return None

    def _get_type_kind(self, type_decl_node, source: bytes) -> str:
        for child in type_decl_node.children:
            if child.type == "type_spec":
                type_node = child.child_by_field_name("type")
                if type_node is not None:
                    if type_node.type == "struct_type":
                        return "struct"
                    if type_node.type == "interface_type":
                        return "interface"
        return "struct"

    def _build_func_signature(self, node, source: bytes) -> str:
        parts = ["func"]
        receiver = node.child_by_field_name("receiver")
        if receiver is not None:
            parts.append(self._node_text(receiver, source))
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            parts.append(self._node_text(name_node, source))
        params = node.child_by_field_name("parameters")
        parts.append(self._node_text(params, source) if params else "()")
        result = node.child_by_field_name("result")
        if result is not None:
            parts.append(f" {self._node_text(result, source)}")
        return "".join(parts)

    def _get_receiver_type(self, node, source: bytes) -> Optional[str]:
        receiver = node.child_by_field_name("receiver")
        if receiver is None:
            return None
        text = self._node_text(receiver, source)
        match = re.search(r"\*?(\w+)\s*\)", text)
        if match:
            return match.group(1)
        tokens = re.findall(r"\w+", text)
        return tokens[-1] if tokens else None

    @staticmethod
    def _get_go_comment(node, source: bytes) -> Optional[str]:
        comments: list[str] = []
        previous = node.prev_named_sibling
        while previous and previous.type == "comment":
            line = source[previous.start_byte:previous.end_byte].decode("utf-8", errors="replace")
            comments.insert(0, line.lstrip("/").strip())
            previous = previous.prev_named_sibling
        return " ".join(comments) if comments else None

    _CALL_QUERY = """
    (call_expression
      function: [
        (identifier) @call.direct
        (selector_expression operand: (_) @call.object field: (field_identifier) @call.method)
      ]
    ) @call.site
    """

    def _extract_calls(self, root, source: bytes, file_path: str) -> list[CallEdge]:
        edges: list[CallEdge] = []
        func_ranges = self._build_func_ranges(root, source)
        captures = self._run_query(self._CALL_QUERY, root)

        for call_node in captures.get("call.site", []):
            call_line = call_node.start_point[0] + 1
            caller_name = self._find_enclosing_func(call_line, func_ranges)
            func_child = call_node.child_by_field_name("function")
            if func_child is None:
                continue
            if func_child.type == "identifier":
                callee = self._node_text(func_child, source)
            elif func_child.type == "selector_expression":
                object_node = func_child.child_by_field_name("operand")
                field_node = func_child.child_by_field_name("field")
                object_text = self._node_text(object_node, source) if object_node else ""
                field_text = self._node_text(field_node, source) if field_node else ""
                callee = f"{object_text}.{field_text}" if object_text else field_text
            else:
                continue

            if callee.split(".")[0] in _GO_BUILTINS:
                continue
            edges.append(
                CallEdge(
                    caller_file=file_path,
                    caller_name=caller_name or "<init>",
                    callee_name=callee,
                    call_line=call_line,
                )
            )
        return edges

    def _build_func_ranges(self, root, source) -> list[tuple[int, int, str]]:
        ranges: list[tuple[int, int, str]] = []
        self._collect_func_ranges(root, source, ranges)
        return sorted(ranges, key=lambda item: item[0])

    def _collect_func_ranges(self, node, source, ranges):
        for child in node.children:
            if child.type in ("function_declaration", "method_declaration"):
                name_node = child.child_by_field_name("name")
                if name_node is not None:
                    name = self._node_text(name_node, source)
                    receiver = child.child_by_field_name("receiver")
                    if receiver is not None:
                        receiver_type = self._get_receiver_type(child, source) or ""
                        name = f"{receiver_type}.{name}"
                    ranges.append((child.start_point[0] + 1, child.end_point[0] + 1, name))
            self._collect_func_ranges(child, source, ranges)

    @staticmethod
    def _find_enclosing_func(line: int, func_ranges) -> Optional[str]:
        best_name = None
        best_size = float("inf")
        for start, end, name in func_ranges:
            if start <= line <= end and (end - start) < best_size:
                best_name = name
                best_size = end - start
        return best_name

    _IMPORT_QUERY = "(import_declaration) @import"

    def _extract_imports(self, root, source: bytes) -> list[ImportDecl]:
        captures = self._run_query(self._IMPORT_QUERY, root)
        results: list[ImportDecl] = []
        for node in captures.get("import", []):
            text = self._node_text(node, source)
            for import_path in re.findall(r'"([^"]+)"', text):
                results.append(ImportDecl(module=import_path))
        return results


_GO_BUILTINS = frozenset(
    {
        "make",
        "new",
        "len",
        "cap",
        "append",
        "copy",
        "delete",
        "close",
        "panic",
        "recover",
        "print",
        "println",
        "complex",
        "real",
        "imag",
        "string",
        "int",
        "float32",
        "float64",
        "bool",
        "byte",
        "rune",
        "error",
    }
)
