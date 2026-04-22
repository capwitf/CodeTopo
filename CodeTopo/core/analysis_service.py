from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from language_support import EXTENSION_TO_LANGUAGE, language_for_path
from llm_providers import resolve_llm_config
from repomap import RepomapBuilder
from visualizer import GraphVisualizer


SUPPORTED_EXTENSIONS = frozenset(EXTENSION_TO_LANGUAGE)


@dataclass
class UploadedFile:
    path: str
    content: str


@dataclass
class AnalysisResult:
    analysis_markdown: str
    mermaid_graph: str
    numbered_code: str
    detected_files: list[str]
    resolved_target_file: str


def analyze_uploaded_files(
    files: list[UploadedFile],
    target_file: str,
    api_key: str,
    provider: str = "deepseek",
    model: str | None = None,
    base_url: str | None = None,
    annotator: Callable[[str, str, str], str] | None = None,
) -> AnalysisResult:
    normalized_target = _normalize_target_input(target_file)
    if not normalized_target:
        raise ValueError("Target file is required.")
    if not api_key:
        raise ValueError("API key is required.")
    if not files:
        raise ValueError("At least one file must be uploaded.")

    normalized_files = _normalize_uploaded_files(files)
    supported_paths = [
        uploaded.path.replace("\\", "/")
        for uploaded in normalized_files
        if Path(uploaded.path).suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    if not supported_paths:
        raise ValueError("No supported source files were uploaded.")

    resolved_target = _resolve_target_file(normalized_target, supported_paths)

    with tempfile.TemporaryDirectory(prefix="ai-doc-generator-") as temp_dir:
        project_root = Path(temp_dir)
        for uploaded in normalized_files:
            relative_path = Path(uploaded.path.replace("\\", "/"))
            full_path = project_root / relative_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(uploaded.content, encoding="utf-8")

        target_path = project_root / resolved_target
        target_code = target_path.read_text(encoding="utf-8")
        language = language_for_path(target_path)

        builder = RepomapBuilder(project_root=str(project_root))
        repomap = builder.build()
        skeleton = repomap.to_text_skeleton(max_tokens_hint=3000)
        mermaid_graph = GraphVisualizer(repomap.call_graph).to_mermaid()
        full_context = f"{skeleton}\n\n### System Call Graph (Mermaid) ###\n{mermaid_graph}"

        if annotator is None:
            from llm_client import AIClient

            llm_config = resolve_llm_config(provider=provider, model=model, base_url=base_url)
            client = AIClient(
                api_key=api_key,
                base_url=llm_config.base_url,
                model=llm_config.model,
            )
            analysis_markdown = client.generate_annotation(
                target_code=target_code,
                repomap_context=full_context,
                language=language,
            )
        else:
            analysis_markdown = annotator(target_code, full_context, language)

        if not analysis_markdown:
            raise RuntimeError("The model returned an empty response.")
        if analysis_markdown.startswith("[API Error]"):
            raise RuntimeError(analysis_markdown)

        numbered_code = "\n".join(
            f"{index + 1:04d} | {line}" for index, line in enumerate(target_code.splitlines())
        )
        return AnalysisResult(
            analysis_markdown=analysis_markdown,
            mermaid_graph=mermaid_graph,
            numbered_code=numbered_code,
            detected_files=sorted(supported_paths),
            resolved_target_file=resolved_target,
        )


def _normalize_uploaded_files(files: list[UploadedFile]) -> list[UploadedFile]:
    normalized = [
        UploadedFile(path=file.path.replace("\\", "/").strip("/"), content=file.content)
        for file in files
    ]
    if not normalized:
        return normalized

    if all(_is_absolute_path(file.path) for file in normalized):
        common_prefix = _common_absolute_prefix([file.path for file in normalized])
        if common_prefix:
            prefix = f"{common_prefix}/"
            return [
                UploadedFile(
                    path=file.path[len(prefix):] if file.path.startswith(prefix) else file.path,
                    content=file.content,
                )
                for file in normalized
            ]

    common_prefix = _common_root_segment([file.path for file in normalized])
    if not common_prefix:
        return normalized

    prefix = f"{common_prefix}/"
    return [
        UploadedFile(
            path=file.path[len(prefix):] if file.path.startswith(prefix) else file.path,
            content=file.content,
        )
        for file in normalized
    ]


def _common_root_segment(paths: list[str]) -> str:
    first_segments = {path.split("/", 1)[0] for path in paths if path}
    return next(iter(first_segments)) if len(first_segments) == 1 else ""


def _normalize_target_input(target_file: str) -> str:
    normalized = target_file.replace("\\", "/").strip()
    if normalized.startswith("file:///"):
        normalized = normalized[8:]
    elif normalized.startswith("file://"):
        normalized = normalized[7:]
    return normalized.strip("/")


def _resolve_target_file(target_file: str, supported_paths: list[str]) -> str:
    if target_file in supported_paths:
        return target_file

    suffix_matches = [
        path for path in supported_paths if target_file.endswith(f"/{path}") or target_file == path
    ]
    if len(suffix_matches) == 1:
        return suffix_matches[0]
    if len(suffix_matches) > 1:
        raise ValueError(
            "Target file is ambiguous. Use a longer path. Matches: "
            + ", ".join(sorted(suffix_matches))
        )

    target_name = Path(target_file).name
    basename_matches = [path for path in supported_paths if Path(path).name == target_name]
    if len(basename_matches) == 1:
        return basename_matches[0]
    if len(basename_matches) > 1:
        raise ValueError(
            "Target file name is ambiguous. Use a relative or absolute path. Matches: "
            + ", ".join(sorted(basename_matches))
        )

    raise ValueError(f"Target file not found in uploaded files: {target_file}")


def _is_absolute_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return normalized.startswith("/") or (
        len(normalized) > 2 and normalized[1] == ":" and normalized[2] == "/"
    )


def _common_absolute_prefix(paths: list[str]) -> str:
    split_paths = [path.replace("\\", "/").split("/") for path in paths if path]
    if not split_paths:
        return ""

    shared_segments: list[str] = []
    for path_segments in zip(*split_paths):
        if len(set(path_segments)) != 1:
            break
        shared_segments.append(path_segments[0])

    return "/".join(shared_segments)
