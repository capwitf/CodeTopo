from __future__ import annotations

from typing import Optional

try:
    import tree_sitter_java as tsjava
    from tree_sitter import Language
except ImportError:
    tsjava = None

from base_parser import BaseParser, CallEdge, ImportDecl, SymbolDef


class JavaParser(BaseParser):
    language_name = "java"

    def _build_language(self):
        if tsjava is None:
            raise RuntimeError("tree-sitter-java is not installed")
        return Language(tsjava.language())

    _SYMBOL_QUERY = """
    [
      (class_declaration       name: (identifier) @class.name)     @class.def
      (interface_declaration   name: (identifier) @interface.name) @interface.def
      (enum_declaration        name: (identifier) @enum.name)      @enum.def
      (method_declaration      name: (identifier) @method.name)    @method.def
      (constructor_declaration name: (identifier) @ctor.name)      @ctor.def
    ]
    """

    def _extract_symbols(self, root, source: bytes, file_path: str) -> list[SymbolDef]:
        symbols: list[SymbolDef] = []
        class_ranges = self._build_class_ranges(root, source)
        captures = self._run_query(self._SYMBOL_QUERY, root)

        for kind_prefix, kind_label in [("class", "class"), ("interface", "class"), ("enum", "class")]:
            for node in captures.get(f"{kind_prefix}.def", []):
                name = self._name_from_captures(node, captures.get(f"{kind_prefix}.name", []), source)
                if not name:
                    continue
                symbols.append(
                    SymbolDef(
                        name=name,
                        kind=kind_label,
                        file_path=file_path,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        signature=f"{kind_prefix} {name}",
                        docstring=self._get_javadoc(node, source),
                    )
                )

        for kind_prefix, kind_label in [("method", "method"), ("ctor", "method")]:
            for node in captures.get(f"{kind_prefix}.def", []):
                name = self._name_from_captures(node, captures.get(f"{kind_prefix}.name", []), source)
                if not name:
                    continue
                parent = self._find_enclosing_class(node.start_point[0] + 1, class_ranges)
                symbols.append(
                    SymbolDef(
                        name=name,
                        kind=kind_label,
                        file_path=file_path,
                        start_line=node.start_point[0] + 1,
                        end_line=node.end_point[0] + 1,
                        signature=self._build_method_sig(node, source),
                        docstring=self._get_javadoc(node, source),
                        parent_class=parent,
                    )
                )
        return symbols

    @staticmethod
    def _name_from_captures(def_node, name_nodes, source: bytes) -> Optional[str]:
        for node in name_nodes:
            current = node.parent
            while current:
                if current.id == def_node.id:
                    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
                current = current.parent
        return None

    def _build_method_sig(self, node, source: bytes) -> str:
        parts: list[str] = []
        for child in node.children:
            if child.type == "modifiers":
                parts.append(self._node_text(child, source))
                break
        type_node = node.child_by_field_name("type")
        if type_node is not None:
            parts.append(self._node_text(type_node, source))
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            parts.append(self._node_text(name_node, source))
        params = node.child_by_field_name("parameters")
        params_text = self._node_text(params, source) if params else "()"
        return f"{' '.join(parts)}{params_text}"

    @staticmethod
    def _get_javadoc(node, source: bytes) -> Optional[str]:
        previous = node.prev_named_sibling
        if previous and previous.type == "block_comment":
            text = source[previous.start_byte:previous.end_byte].decode("utf-8", errors="replace")
            if text.startswith("/**"):
                lines = text.strip("/**").strip("*/").strip().splitlines()
                cleaned = [line.strip().lstrip("*").strip() for line in lines]
                return " ".join(line for line in cleaned if line)
        return None

    def _build_class_ranges(self, root, source) -> list[tuple[int, int, str]]:
        ranges: list[tuple[int, int, str]] = []
        self._collect_class_ranges(root, source, ranges)
        return sorted(ranges, key=lambda item: item[0])

    def _collect_class_ranges(self, node, source, ranges):
        for child in node.children:
            if child.type in ("class_declaration", "interface_declaration", "enum_declaration"):
                name_node = child.child_by_field_name("name")
                if name_node is not None:
                    ranges.append(
                        (
                            child.start_point[0] + 1,
                            child.end_point[0] + 1,
                            self._node_text(name_node, source),
                        )
                    )
            self._collect_class_ranges(child, source, ranges)

    @staticmethod
    def _find_enclosing_class(line, class_ranges) -> Optional[str]:
        best_name = None
        best_size = float("inf")
        for start, end, name in class_ranges:
            if start <= line <= end and (end - start) < best_size:
                best_name = name
                best_size = end - start
        return best_name

    _CALL_QUERY = "(method_invocation name: (identifier) @call.name) @call.site"

    def _extract_calls(self, root, source: bytes, file_path: str) -> list[CallEdge]:
        edges: list[CallEdge] = []
        method_ranges = self._build_method_ranges(root, source)
        captures = self._run_query(self._CALL_QUERY, root)

        for call_node in captures.get("call.site", []):
            call_line = call_node.start_point[0] + 1
            caller = self._find_enclosing_method(call_line, method_ranges)
            name_node = call_node.child_by_field_name("name")
            if name_node is None:
                continue
            callee_base = self._node_text(name_node, source)
            if callee_base in _JAVA_COMMON_METHODS:
                continue
            object_node = call_node.child_by_field_name("object")
            callee = (
                f"{self._node_text(object_node, source)}.{callee_base}"
                if object_node is not None
                else callee_base
            )
            edges.append(
                CallEdge(
                    caller_file=file_path,
                    caller_name=caller or "<static>",
                    callee_name=callee,
                    call_line=call_line,
                )
            )
        return edges

    def _build_method_ranges(self, root, source) -> list[tuple[int, int, str]]:
        ranges: list[tuple[int, int, str]] = []
        self._collect_method_ranges(root, source, ranges)
        return sorted(ranges, key=lambda item: item[0])

    def _collect_method_ranges(self, node, source, ranges):
        for child in node.children:
            if child.type in ("method_declaration", "constructor_declaration"):
                name_node = child.child_by_field_name("name")
                if name_node is not None:
                    ranges.append(
                        (
                            child.start_point[0] + 1,
                            child.end_point[0] + 1,
                            self._node_text(name_node, source),
                        )
                    )
            self._collect_method_ranges(child, source, ranges)

    @staticmethod
    def _find_enclosing_method(line, method_ranges) -> Optional[str]:
        best_name = None
        best_size = float("inf")
        for start, end, name in method_ranges:
            if start <= line <= end and (end - start) < best_size:
                best_name = name
                best_size = end - start
        return best_name

    _IMPORT_QUERY = "(import_declaration) @import"

    def _extract_imports(self, root, source: bytes) -> list[ImportDecl]:
        captures = self._run_query(self._IMPORT_QUERY, root)
        results: list[ImportDecl] = []
        for node in captures.get("import", []):
            text = self._node_text(node, source).replace("import ", "").replace("static ", "").rstrip(";")
            results.append(ImportDecl(module=text.strip()))
        return results


_JAVA_COMMON_METHODS = frozenset(
    {
        "toString",
        "equals",
        "hashCode",
        "compareTo",
        "clone",
        "finalize",
        "wait",
        "notify",
        "notifyAll",
        "getClass",
        "println",
        "print",
        "printf",
        "format",
        "append",
        "add",
        "get",
        "set",
        "size",
        "isEmpty",
        "contains",
        "remove",
        "put",
        "containsKey",
        "keySet",
        "length",
        "charAt",
        "substring",
        "indexOf",
        "split",
        "trim",
        "valueOf",
        "parseInt",
    }
)
