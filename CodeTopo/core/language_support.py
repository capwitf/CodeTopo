from __future__ import annotations

from pathlib import Path


EXTENSION_TO_LANGUAGE = {
    ".py": "python",
    ".java": "java",
    ".go": "go",
    ".c": "c",
    ".h": "c",
}


def language_for_path(path: str | Path) -> str:
    suffix = Path(path).suffix.lower()
    return EXTENSION_TO_LANGUAGE.get(suffix, suffix.lstrip("."))
