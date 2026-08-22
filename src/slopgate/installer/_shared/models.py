"""Shared installer request objects."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ContainedWrite:
    """Write policy for a file that must stay inside an install root."""

    root: Path
    label: str
    backup: bool = True


@dataclass(frozen=True, slots=True)
class InstallAt:
    """Site options shared by platform install helpers."""

    root: Path
    dry_run: bool = False


@dataclass(frozen=True, slots=True)
class OwnedHooksWrite:
    """Load-or-preview policy for merging owned hooks into a JSON document."""

    label: str
    hooks: dict[str, list[dict[str, object]]]
    dry_run: bool
    verb: str


@dataclass(frozen=True, slots=True)
class HooksUninstall:
    """Uninstall policy for a platform hooks.json file."""

    label: str
    remove_owned: Callable[[object], dict[str, list[dict[str, object]]]]
    dry_run: bool = False
    root: Path | None = None
