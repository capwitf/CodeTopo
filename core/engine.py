from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from repomap import Repomap, RepomapBuilder


class RepomapEngine:
    def __init__(
        self,
        project_root: str,
        exclude_patterns: list[str] | None = None,
        verbose: bool = False,
    ) -> None:
        self.project_root = str(Path(project_root).resolve())
        self.builder = RepomapBuilder(
            project_root=self.project_root,
            exclude_patterns=exclude_patterns,
            verbose=verbose,
        )
        self.verbose = verbose
        self._repomap: Repomap | None = None

    def run(self) -> Repomap:
        started_at = time.perf_counter()
        self._repomap = self.builder.build()
        elapsed = time.perf_counter() - started_at
        if self.verbose:
            stats = self._repomap.stats()
            print(
                f"\n[RepomapEngine] Build finished in {elapsed:.2f}s\n"
                f"  files: {stats.get('files', '-')}\n"
                f"  symbols: {stats.get('symbols', '-')}\n"
                f"  total calls: {stats.get('total_calls', '-')}\n"
                f"  cross-file calls: {stats.get('cross_file_calls', '-')}\n"
                f"  resolution rate: {stats.get('resolution_rate', '-')}"
            )
        return self._repomap

    @property
    def repomap(self) -> Repomap | None:
        return self._repomap

    def export_json(self, output_path: str) -> None:
        if self._repomap is None:
            raise RuntimeError("Run the engine before exporting.")
        Path(output_path).write_text(self._repomap.to_json(), encoding="utf-8")
        print(f"Exported JSON to {output_path}")

    def export_skeleton(self, output_path: str, max_tokens: int = 4000) -> None:
        if self._repomap is None:
            raise RuntimeError("Run the engine before exporting.")
        Path(output_path).write_text(
            self._repomap.to_text_skeleton(max_tokens_hint=max_tokens),
            encoding="utf-8",
        )
        print(f"Exported skeleton to {output_path}")


def _build_cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="repomap-engine", description="Repository map builder")
    parser.add_argument("--root", required=True, help="Project root path")
    parser.add_argument("--json", metavar="FILE", help="Export graph JSON")
    parser.add_argument("--skeleton", metavar="FILE", help="Export text skeleton")
    parser.add_argument("--max-tokens", type=int, default=4000)
    parser.add_argument("--cross-file-only", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--exclude", nargs="*", metavar="PATTERN")
    return parser


def main() -> None:
    args = _build_cli().parse_args()
    engine = RepomapEngine(
        project_root=args.root,
        exclude_patterns=args.exclude or None,
        verbose=args.verbose,
    )
    repomap = engine.run()
    if not args.verbose:
        stats = repomap.stats()
        print(
            f"Analysis finished: {stats.get('files')} files, "
            f"{stats.get('symbols')} symbols, "
            f"{stats.get('cross_file_calls')} cross-file calls"
        )
    if args.json:
        engine.export_json(args.json)
    if args.skeleton:
        skeleton = repomap.to_text_skeleton(
            max_tokens_hint=args.max_tokens,
            only_cross_file=args.cross_file_only,
        )
        Path(args.skeleton).write_text(skeleton, encoding="utf-8")
        print(f"Exported skeleton to {args.skeleton}")
    elif not args.json:
        print(
            repomap.to_text_skeleton(
                max_tokens_hint=args.max_tokens,
                only_cross_file=args.cross_file_only,
            )
        )


if __name__ == "__main__":
    main()
