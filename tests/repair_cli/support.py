"""Shared captures for repair CLI tests."""

from __future__ import annotations

from pathlib import Path


class ScopedLintCapture:
    """Capture scoped lint arguments while returning a configured status."""

    def __init__(self, returncode: int = 0) -> None:
        self.returncode = returncode
        self.calls: list[tuple[Path, tuple[str, ...], tuple[str, ...]]] = []

    def __call__(self, cwd: Path, paths: list[str], rule_ids: list[str]) -> int:
        self.calls.append((cwd, tuple(paths), tuple(rule_ids)))
        return self.returncode
