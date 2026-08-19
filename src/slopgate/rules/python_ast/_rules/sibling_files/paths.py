"""Resolve candidate paths and shared prefixes for flat sibling modules."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from slopgate.context import HookContext

_IGNORED_PREFIXES = frozenset({"test"})


class FlatSiblingFindingInput(NamedTuple):
    parent: Path
    prefix: str
    files: list[str]
    decision: str
    reason: str


def flat_sibling_resolve_candidate_path(ctx: HookContext, path_value: str) -> Path:
    """Resolve a candidate path against the hook working directory."""
    raw_path = Path(path_value)
    return raw_path if raw_path.is_absolute() else (Path(ctx.cwd) / raw_path).resolve()


def prefix_for_name(name: str) -> str | None:
    """Return the package prefix for prefix_*.py and _prefix_*.py names."""
    import re

    match = re.match("^_?([a-z][a-z0-9]*)_[a-z0-9_]+\\.pyi?$", name)
    if match is None:
        return None
    prefix = match.group(1)
    if prefix in _IGNORED_PREFIXES:
        return None
    return prefix
