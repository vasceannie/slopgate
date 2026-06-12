"""Lint helper path accessors."""

from __future__ import annotations

from pathlib import Path

from slopgate.lint._config import get_config


def project_root() -> Path:
    return get_config().project_root


def src_root() -> Path:
    return get_config().src_root


def src_roots() -> tuple[Path, ...]:
    return get_config().src_roots


def tests_root() -> Path:
    return get_config().tests_root


def test_roots() -> tuple[Path, ...]:
    return get_config().test_roots


def relative_path(p: Path) -> str:
    """Return a POSIX relative path string from the project root."""
    try:
        return p.resolve().relative_to(project_root().resolve()).as_posix()
    except ValueError:
        return p.as_posix()
