"""Shared captures for repair CLI tests."""

from __future__ import annotations

from pathlib import Path

from slopgate._types import ObjectDict


class ScopedLintCapture:
    """Capture scoped lint arguments while returning a configured status."""

    def __init__(self, returncode: int = 0) -> None:
        self.returncode = returncode
        self.calls: list[tuple[Path, tuple[ObjectDict, ...]]] = []

    def __call__(self, cwd: Path, targets: list[ObjectDict]) -> int:
        self.calls.append((cwd, tuple(dict(target) for target in targets)))
        return self.returncode
