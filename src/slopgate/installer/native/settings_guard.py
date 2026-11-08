"""Rollback of host-owned settings files that a native registration touched.

Native plugin managers record registrations in JSON files they create on first
use and leave behind, emptied, when the registration is removed. A failed
first-time install would otherwise leave those files (and the directories
created for them) in the user's project, so each transaction snapshots them
before the first registration command runs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from slopgate.installer.native.artifacts import (
    ArtifactSnapshot,
    capture_artifact,
    missing_directories,
    remove_empty_directories,
    restore_artifact,
)

__all__ = [
    "NativeSettingsFile",
    "SettingsGuard",
    "capture_guards",
    "restore_guards",
]


@dataclass(frozen=True, slots=True)
class NativeSettingsFile:
    """A host-owned JSON file whose registry a registration command rewrites.

    ``registry_keys`` hold the registrations (empty once everything is
    unregistered); ``inert_keys`` are bookkeeping scalars the host writes next
    to them. Any other key is treated as user content.
    """

    path: Path
    registry_keys: frozenset[str]
    inert_keys: frozenset[str] = frozenset()


@dataclass(frozen=True, slots=True)
class SettingsGuard:
    """The pre-transaction state of one native settings file."""

    settings: NativeSettingsFile
    snapshot: ArtifactSnapshot
    created_directories: tuple[Path, ...]


def capture_guards(files: tuple[NativeSettingsFile, ...]) -> tuple[SettingsGuard, ...]:
    """Record each file's bytes (or absence) and the directories it would create."""
    return tuple(
        SettingsGuard(
            settings=settings,
            snapshot=capture_artifact(settings.path),
            created_directories=missing_directories(settings.path.parent),
        )
        for settings in files
    )


def restore_guards(guards: tuple[SettingsGuard, ...]) -> None:
    """Return captured files to their prior state once nothing is registered.

    A file that existed is rewritten with its original bytes; one that did not
    is deleted only while it holds nothing but emptied registry keys. Directories
    created for those files are removed last, once every file in them is gone.
    Raises ``OSError`` for anything that had to be left in place.
    """
    for guard in guards:
        _restore_file(guard)
    created = {path for guard in guards for path in guard.created_directories}
    ordered = tuple(sorted(created, key=lambda path: len(path.parts), reverse=True))
    if remove_empty_directories(ordered) != 0:
        raise OSError(
            "directories created for native settings are not empty: "
            + ", ".join(str(path) for path in ordered)
        )


def _restore_file(guard: SettingsGuard) -> None:
    path = guard.settings.path
    if guard.snapshot.existed:
        if path.exists() and path.read_bytes() == guard.snapshot.content:
            return
        restore_artifact(path, guard.snapshot)
        return
    if not path.exists():
        return
    if not _only_emptied_registry(guard.settings):
        raise OSError(f"{path} holds settings Slopgate did not create; left in place")
    restore_artifact(path, guard.snapshot)


def _only_emptied_registry(settings: NativeSettingsFile) -> bool:
    try:
        parsed = cast(object, json.loads(settings.path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return False
    if not isinstance(parsed, dict):
        return False
    document = cast(dict[str, object], parsed)
    for key, value in document.items():
        if key in settings.registry_keys:
            if value:
                return False
        elif key not in settings.inert_keys:
            return False
    return True
