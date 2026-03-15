from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))

from base_parser import CallEdge, SymbolDef
from call_resolver import CallGraph, ResolvedCall
from visualizer import GraphVisualizer


class GraphVisualizerTests(unittest.TestCase):
    def test_mermaid_uses_short_node_ids_and_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-doc-generator-") as temp_dir:
            root = Path(temp_dir)
            caller_file = str(root / "sample" / "main.py")
            callee_file = str(root / "sample" / "helper.py")

            caller_def = SymbolDef(
                name="run",
                kind="function",
                file_path=caller_file,
                start_line=1,
                end_line=2,
                signature="def run():",
            )
            callee_def = SymbolDef(
                name="greet",
                kind="function",
                file_path=callee_file,
                start_line=1,
                end_line=2,
                signature="def greet():",
            )
            edge = CallEdge(
                caller_file=caller_file,
                caller_name="run",
                callee_name="greet",
                call_line=2,
            )
            graph = CallGraph(
                nodes={
                    f"{caller_file}::run": caller_def,
                    f"{callee_file}::greet": callee_def,
                },
                edges=[ResolvedCall(edge=edge, caller_def=caller_def, callee_def=callee_def)],
            )

            mermaid = GraphVisualizer(graph).to_mermaid()

            self.assertIn("graph TD", mermaid)
            self.assertIn("main.py", mermaid)
            self.assertIn("helper.py", mermaid)
            self.assertNotIn(temp_dir.replace("\\", "/"), mermaid)
            self.assertRegex(mermaid, r'n_[0-9a-f]{10}\["run<br/>main.py"\]')

    def test_mermaid_wraps_long_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai-doc-generator-") as temp_dir:
            root = Path(temp_dir)
            caller_file = str(root / "pkg" / "entry.py")
            callee_file = str(
                root
                / "pkg"
                / "services"
                / "deeply"
                / "nested"
                / "very_long_module_name.py"
            )

            caller_def = SymbolDef(
                name="run",
                kind="function",
                file_path=caller_file,
                start_line=1,
                end_line=2,
                signature="def run():",
            )
            callee_def = SymbolDef(
                name="handle_request",
                kind="function",
                file_path=callee_file,
                start_line=1,
                end_line=2,
                signature="def handle_request():",
            )
            edge = CallEdge(
                caller_file=caller_file,
                caller_name="run",
                callee_name="handle_request",
                call_line=2,
            )
            graph = CallGraph(
                nodes={
                    f"{caller_file}::run": caller_def,
                    f"{callee_file}::handle_request": callee_def,
                },
                edges=[ResolvedCall(edge=edge, caller_def=caller_def, callee_def=callee_def)],
            )

            mermaid = GraphVisualizer(graph).to_mermaid()

            self.assertIn("services/deeply/nested", mermaid)
            self.assertIn("very_long_module_name.py", mermaid)
            self.assertIn("services/deeply/nested<br/>very_long_module_name.py", mermaid)


if __name__ == "__main__":
    unittest.main()
