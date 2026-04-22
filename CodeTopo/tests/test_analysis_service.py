from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "core"))

from analysis_service import UploadedFile, analyze_uploaded_files


class AnalysisServiceTests(unittest.TestCase):
    def test_rejects_missing_target(self) -> None:
        with self.assertRaisesRegex(ValueError, "Target file is required"):
            analyze_uploaded_files([], "", "key", annotator=lambda *_: "ok")

    def test_rejects_missing_supported_files(self) -> None:
        files = [UploadedFile(path="README.md", content="# hi")]
        with self.assertRaisesRegex(ValueError, "No supported source files"):
            analyze_uploaded_files(files, "README.md", "key", annotator=lambda *_: "ok")

    def test_returns_structured_result(self) -> None:
        files = [
            UploadedFile(
                path="sample-project/sample/main.py",
                content=(
                    "from helper import greet\n\n"
                    "def run():\n"
                    "    greet()\n"
                ),
            ),
            UploadedFile(
                path="sample-project/sample/helper.py",
                content="def greet():\n    return 'hi'\n",
            ),
        ]

        result = analyze_uploaded_files(
            files=files,
            target_file="sample/main.py",
            api_key="test-key",
            annotator=lambda target_code, repomap_context, language: (
                f"# Mocked\n\nLanguage: {language}\n\nTarget size: {len(target_code)}\n\n{repomap_context[:40]}"
            ),
        )

        self.assertIn("# Mocked", result.analysis_markdown)
        self.assertIn("graph TD", result.mermaid_graph)
        self.assertIn("0001 | from helper import greet", result.numbered_code)
        self.assertEqual(result.detected_files, ["sample/helper.py", "sample/main.py"])
        self.assertEqual(result.resolved_target_file, "sample/main.py")

    def test_accepts_absolute_target_path(self) -> None:
        files = [
            UploadedFile(
                path="sample-project/sample/main.py",
                content="def run():\n    return 'ok'\n",
            ),
        ]

        result = analyze_uploaded_files(
            files=files,
            target_file="C:/Users/T/Desktop/AI-Doc-Generator1.0/sample-project/sample/main.py",
            api_key="test-key",
            annotator=lambda *_: "# Mocked",
        )

        self.assertEqual(result.resolved_target_file, "sample/main.py")

    def test_accepts_unique_basename_target(self) -> None:
        files = [
            UploadedFile(path="sample-project/pkg/main.py", content="def a():\n    return 1\n"),
            UploadedFile(path="sample-project/pkg/helper.py", content="def b():\n    return 2\n"),
        ]

        result = analyze_uploaded_files(
            files=files,
            target_file="helper.py",
            api_key="test-key",
            annotator=lambda *_: "# Mocked",
        )

        self.assertEqual(result.resolved_target_file, "pkg/helper.py")

    def test_rejects_ambiguous_basename_target(self) -> None:
        files = [
            UploadedFile(path="sample-project/pkg1/helper.py", content="def a():\n    return 1\n"),
            UploadedFile(path="sample-project/pkg2/helper.py", content="def b():\n    return 2\n"),
        ]

        with self.assertRaisesRegex(ValueError, "Target file name is ambiguous"):
            analyze_uploaded_files(
                files=files,
                target_file="helper.py",
                api_key="test-key",
                annotator=lambda *_: "# Mocked",
            )


if __name__ == "__main__":
    unittest.main()
