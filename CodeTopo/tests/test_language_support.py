from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))

from language_support import EXTENSION_TO_LANGUAGE, language_for_path


class LanguageSupportTests(unittest.TestCase):
    def test_maps_c_extensions_to_c_language(self) -> None:
        self.assertEqual(language_for_path("src/main.c"), "c")
        self.assertEqual(language_for_path("include/main.h"), "c")

    def test_supported_extension_table_contains_c_entries(self) -> None:
        self.assertEqual(EXTENSION_TO_LANGUAGE[".c"], "c")
        self.assertEqual(EXTENSION_TO_LANGUAGE[".h"], "c")


if __name__ == "__main__":
    unittest.main()
