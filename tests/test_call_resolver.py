from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))

from repomap import RepomapBuilder


class CallResolverTests(unittest.TestCase):
    def test_resolves_imported_python_symbol(self) -> None:
        with tempfile.TemporaryDirectory(prefix="call-resolver-") as temp_dir:
            root = Path(temp_dir)
            (root / "main.py").write_text(
                "from helper import greet\n\n"
                "def run():\n"
                "    greet()\n",
                encoding="utf-8",
            )
            (root / "helper.py").write_text(
                "def greet():\n"
                "    return 'hi'\n",
                encoding="utf-8",
            )

            repomap = RepomapBuilder(str(root)).build()
            resolved_edges = repomap.call_graph.resolved_edges

            self.assertEqual(len(resolved_edges), 1)
            self.assertEqual(Path(resolved_edges[0].callee_def.file_path).name, "helper.py")

    def test_does_not_guess_cross_file_target_without_import(self) -> None:
        with tempfile.TemporaryDirectory(prefix="call-resolver-") as temp_dir:
            root = Path(temp_dir)
            (root / "main.py").write_text(
                "def run():\n"
                "    helper()\n",
                encoding="utf-8",
            )
            (root / "helper.py").write_text(
                "def helper():\n"
                "    return 'hi'\n",
                encoding="utf-8",
            )

            repomap = RepomapBuilder(str(root)).build()

            self.assertEqual(len(repomap.call_graph.resolved_edges), 0)

    def test_imported_module_matching_requires_exact_module_path(self) -> None:
        with tempfile.TemporaryDirectory(prefix="call-resolver-") as temp_dir:
            root = Path(temp_dir)
            (root / "app.py").write_text(
                "import service\n\n"
                "def run():\n"
                "    service.handle()\n",
                encoding="utf-8",
            )
            (root / "service_extra.py").write_text(
                "def handle():\n"
                "    return 'wrong'\n",
                encoding="utf-8",
            )

            repomap = RepomapBuilder(str(root)).build()

            self.assertEqual(len(repomap.call_graph.resolved_edges), 0)


if __name__ == "__main__":
    unittest.main()
