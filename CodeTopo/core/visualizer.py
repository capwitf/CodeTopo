from __future__ import annotations

import hashlib
import json
import os
import textwrap

from call_resolver import CallGraph


class GraphVisualizer:
    def __init__(self, call_graph: CallGraph):
        self.graph = call_graph
        self._display_paths = self._build_display_paths()

    def to_mermaid(self) -> str:
        if not self.graph.edges:
            return 'graph TD\n    empty["No calls detected"]'

        lines = ["graph TD"]
        added_edges: set[tuple[str, str]] = set()

        for call in self.graph.resolved_edges:
            caller_node = self._node_id(call.edge.caller_file, call.edge.caller_name)
            callee_node = self._node_id(call.callee_def.file_path, call.callee_def.qualified_name)

            edge_signature = (caller_node, callee_node)
            if edge_signature in added_edges:
                continue

            caller_label = self._format_node_label(
                call.edge.caller_name.split(".")[-1],
                call.edge.caller_file,
            )
            callee_label = self._format_node_label(call.callee_def.name, call.callee_def.file_path)
            lines.append(
                f'    {caller_node}["{caller_label}"] --> {callee_node}["{callee_label}"]'
            )
            added_edges.add(edge_signature)

        return "\n".join(lines)

    def to_d3_json(self) -> str:
        nodes_dict: dict[str, dict[str, object]] = {}
        links: list[dict[str, object]] = []

        for call in self.graph.resolved_edges:
            caller_id = f"{call.edge.caller_file}::{call.edge.caller_name}"
            callee_id = f"{call.callee_def.file_path}::{call.callee_def.qualified_name}"

            if caller_id not in nodes_dict:
                nodes_dict[caller_id] = {
                    "id": caller_id,
                    "name": call.edge.caller_name.split(".")[-1],
                    "file": self._display_paths.get(call.edge.caller_file, call.edge.caller_file),
                    "type": "caller",
                }
            if callee_id not in nodes_dict:
                nodes_dict[callee_id] = {
                    "id": callee_id,
                    "name": call.callee_def.name,
                    "file": self._display_paths.get(call.callee_def.file_path, call.callee_def.file_path),
                    "type": call.callee_def.kind,
                }

            links.append(
                {
                    "source": caller_id,
                    "target": callee_id,
                    "is_cross_file": call.is_cross_file,
                }
            )

        return json.dumps({"nodes": list(nodes_dict.values()), "links": links}, ensure_ascii=False, indent=2)

    def _build_display_paths(self) -> dict[str, str]:
        file_paths = sorted(self._collect_file_paths())
        if not file_paths:
            return {}

        normalized_paths = [path.replace("\\", "/") for path in file_paths]
        try:
            common_root = os.path.commonpath(normalized_paths)
        except ValueError:
            common_root = ""

        display_paths: dict[str, str] = {}
        for original_path, normalized_path in zip(file_paths, normalized_paths):
            if common_root:
                relative_path = os.path.relpath(normalized_path, common_root).replace("\\", "/")
                if not relative_path.startswith("../"):
                    display_paths[original_path] = relative_path
                    continue
            display_paths[original_path] = normalized_path
        return display_paths

    def _collect_file_paths(self) -> set[str]:
        file_paths: set[str] = set()
        for call in self.graph.resolved_edges:
            file_paths.add(call.edge.caller_file)
            file_paths.add(call.callee_def.file_path)
        for symbol in self.graph.nodes.values():
            file_paths.add(symbol.file_path)
        return file_paths

    def _node_id(self, file_path: str, symbol_name: str) -> str:
        raw_key = f"{self._display_paths.get(file_path, file_path)}::{symbol_name}"
        digest = hashlib.sha1(raw_key.encode("utf-8")).hexdigest()[:10]
        return f"n_{digest}"

    def _format_node_label(self, symbol_name: str, file_path: str) -> str:
        display_path = self._display_paths.get(file_path, file_path).replace("\\", "/")
        safe_symbol = self._escape_label(self._wrap_text(symbol_name, width=22))
        safe_path = self._escape_label(self._wrap_path(display_path, width=24))
        return f"{safe_symbol}<br/>{safe_path}"

    @staticmethod
    def _wrap_text(text: str, width: int) -> str:
        lines = textwrap.wrap(
            text,
            width=width,
            break_long_words=True,
            break_on_hyphens=False,
        )
        return "<br/>".join(lines) if lines else text

    @classmethod
    def _wrap_path(cls, path: str, width: int) -> str:
        parts = path.split("/")
        if len(parts) <= 1:
            return cls._wrap_text(path, width)

        lines: list[str] = []
        current = ""
        for part in parts:
            candidate = part if not current else f"{current}/{part}"
            if current and len(candidate) > width:
                lines.append(current)
                current = cls._wrap_text(part, width)
                continue
            if len(part) > width:
                if current:
                    lines.append(current)
                current = cls._wrap_text(part, width)
                continue
            current = candidate

        if current:
            lines.append(current)

        return "<br/>".join(lines)

    @staticmethod
    def _escape_label(text: str) -> str:
        return text.replace('"', "'")
