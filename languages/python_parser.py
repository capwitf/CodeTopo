from __future__ import annotations

from typing import Optional

try:
    import tree_sitter_python as tspython
    from tree_sitter import Language
except ImportError:
    tspython = None

from base_parser import BaseParser, CallEdge, ImportDecl, SymbolDef


class PythonParser(BaseParser):
    language_name = "python"

    def _build_language(self):
        if tspython is None:
            raise RuntimeError("tree-sitter-python is not installed")
        return Language(tspython.language())

    def _extract_symbols(self, root, source: bytes, file_path: str) -> list[SymbolDef]:
        symbols: list[SymbolDef] = []
        self._walk_definitions(root, source, file_path, symbols, parent_class=None)
        return symbols

    def _walk_definitions(self, node, source, file_path, symbols, parent_class):
        for child in node.children:
            if child.type == "function_definition":
                symbol = self._parse_function(child, source, file_path, parent_class)
                if symbol is not None:
                    symbols.append(symbol)
                    self._walk_definitions(child, source, file_path, symbols, parent_class)
            elif child.type == "class_definition":
                name_node = child.child_by_field_name("name")
                class_name = self._node_text(name_node, source) if name_node else "<anonymous>"
                symbols.append(
                    SymbolDef(
                        name=class_name,
                        kind="class",
                        file_path=file_path,
                        start_line=child.start_point[0] + 1,
                        end_line=child.end_point[0] + 1,
                        signature=f"class {class_name}",
                        docstring=self._get_docstring(child, source),
                    )
                )
                body = child.child_by_field_name("body")
                if body is not None:
                    self._walk_definitions(body, source, file_path, symbols, class_name)
            else:
                self._walk_definitions(child, source, file_path, symbols, parent_class)

    def _parse_function(self, node, source, file_path, parent_class) -> Optional[SymbolDef]:
        name_node = node.child_by_field_name("name")
        if name_node is None:
            return None
        name = self._node_text(name_node, source)
        params = node.child_by_field_name("parameters")
        params_text = self._node_text(params, source) if params else "()"
        ret = node.child_by_field_name("return_type")
        ret_hint = f" -> {self._node_text(ret, source)}" if ret else ""
        return SymbolDef(
            name=name,
            kind="method" if parent_class else "function",
            file_path=file_path,
            start_line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            signature=f"def {name}{params_text}{ret_hint}",
            docstring=self._get_docstring(node, source),
            parent_class=parent_class,
        )

    @staticmethod
    def _get_docstring(node, source: bytes) -> Optional[str]:
        body = node.child_by_field_name("body")
        if body is None:
            return None
        for child in body.children:
            if child.type != "expression_statement":
                continue
            for sub in child.children:
                if sub.type == "string":
                    raw = source[sub.start_byte:sub.end_byte].decode("utf-8", errors="replace")
                    return raw.strip('"""').strip("'''").strip('"').strip("'").strip()
        return None

    _CALL_QUERY = """
    (call
      function: [
        (identifier)
        (attribute)
      ] @call.func) @call.site
    """

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
            if not callee_name or callee_name in _PYTHON_BUILTINS:
                continue

            edges.append(
                CallEdge(
                    caller_file=file_path,
                    caller_name=caller_name or "<module>",
                    callee_name=callee_name,
                    call_line=call_line,
                )
            )
        return edges

    def _build_function_ranges(self, root, source) -> list[tuple[int, int, str]]:
        ranges: list[tuple[int, int, str]] = []
        self._collect_ranges(root, source, ranges, "")
        return sorted(ranges, key=lambda item: item[0])

    def _collect_ranges(self, node, source, ranges, prefix):
        for child in node.children:
            if child.type == "function_definition":
                name_node = child.child_by_field_name("name")
                name = self._node_text(name_node, source) if name_node else "?"
                qualified_name = f"{prefix}.{name}" if prefix else name
                ranges.append((child.start_point[0] + 1, child.end_point[0] + 1, qualified_name))
                self._collect_ranges(child, source, ranges, qualified_name)
            elif child.type == "class_definition":
                name_node = child.child_by_field_name("name")
                name = self._node_text(name_node, source) if name_node else "?"
                body = child.child_by_field_name("body")
                if body is not None:
                    self._collect_ranges(body, source, ranges, name)
            else:
                self._collect_ranges(child, source, ranges, prefix)

    @staticmethod
    def _find_enclosing_function(line: int, func_ranges) -> Optional[str]:
        best_name = None
        best_size = float("inf")
        for start, end, name in func_ranges:
            if start <= line <= end and (end - start) < best_size:
                best_name = name
                best_size = end - start
        return best_name

    def _extract_imports(self, root, source: bytes) -> list[ImportDecl]:
        results: list[ImportDecl] = []

        def walk(node):
            if node.type == "import_statement":
                for child in node.children:
                    if child.type == "dotted_name":
                        results.append(ImportDecl(module=self._node_text(child, source)))
                    elif child.type == "aliased_import":
                        name_node = child.child_by_field_name("name")
                        alias_node = child.child_by_field_name("alias")
                        if name_node is not None and alias_node is not None:
                            results.append(
                                ImportDecl(
                                    module=self._node_text(name_node, source),
                                    alias=self._node_text(alias_node, source),
                                )
                            )
            elif node.type == "import_from_statement":
                module_node = node.child_by_field_name("module_name")
                module_name = self._node_text(module_node, source) if module_node else ""

                for child in node.children:
                    if child.type == "dotted_name" and child != module_node:
                        results.append(
                            ImportDecl(module=module_name, name=self._node_text(child, source))
                        )
                    elif child.type == "aliased_import":
                        name_node = child.child_by_field_name("name")
                        alias_node = child.child_by_field_name("alias")
                        if name_node is not None and alias_node is not None:
                            results.append(
                                ImportDecl(
                                    module=module_name,
                                    name=self._node_text(name_node, source),
                                    alias=self._node_text(alias_node, source),
                                )
                            )
                    elif child.type == "wildcard_import":
                        results.append(ImportDecl(module=module_name, name="*"))
            for child in node.children:
                walk(child)

        walk(root)
        return results


_PYTHON_BUILTINS = frozenset(
    {
        "print",
        "len",
        "range",
        "enumerate",
        "zip",
        "map",
        "filter",
        "isinstance",
        "issubclass",
        "type",
        "id",
        "hash",
        "repr",
        "str",
        "int",
        "float",
        "bool",
        "list",
        "dict",
        "set",
        "tuple",
        "bytes",
        "open",
        "hasattr",
        "getattr",
        "setattr",
        "delattr",
        "vars",
        "dir",
        "super",
        "object",
        "property",
        "Exception",
        "ValueError",
        "TypeError",
    }
)
