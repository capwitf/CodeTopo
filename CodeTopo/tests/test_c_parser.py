from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "languages"))


@unittest.skipUnless(importlib.util.find_spec("tree_sitter_c"), "tree_sitter_c is not installed")
class CParserTests(unittest.TestCase):
    def setUp(self) -> None:
        from c_parser import CParser

        self.parser = CParser()

    def test_extracts_functions_calls_and_includes(self) -> None:
        source = """
        #include "demo.h"
        #include <stdio.h>

        static int helper(void) {
            return 1;
        }

        int run(void) {
            return helper();
        }
        """

        result = self.parser.parse_source(source, "demo.c")

        function_names = [symbol.name for symbol in result.symbols if symbol.kind == "function"]
        self.assertIn("helper", function_names)
        self.assertIn("run", function_names)
        self.assertTrue(
            any(edge.caller_name == "run" and edge.callee_name == "helper" for edge in result.call_sites)
        )
        self.assertEqual([str(item) for item in result.imports], ["demo.h", "stdio.h"])


if __name__ == "__main__":
    unittest.main()
