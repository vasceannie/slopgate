"""Byte-and-mode snapshots for installer-owned files."""

from __future__ import annotations

import stat
from dataclasses import dataclass
from pathlib import Path

from slopgate.installer._shared import UnsafeInstallPathError
from slopgate.util.platform import is_link_or_junction

__all__ = [
    "ArtifactSnapshot",
    "capture_artifact",
    "missing_directories",
    "remove_empty_directories",
    "restore_artifact",
    "unsafe_anchor_issue",
]


@dataclass(frozen=True, slots=True)
class ArtifactSnapshot:
    """Original bytes and mode for one installer artifact."""

    existed: bool
    content: bytes | None
    mode: int | None


def capture_artifact(path: Path) -> ArtifactSnapshot:
    """Record a regular file's bytes and mode, or its absence."""
    if not path.exists():
        return ArtifactSnapshot(False, None, None)
    if not path.is_file():
        raise UnsafeInstallPathError(f"Refusing to replace non-file artifact: {path}")
    return ArtifactSnapshot(
        existed=True,
        content=path.read_bytes(),
        mode=stat.S_IMODE(path.stat().st_mode),
    )


def restore_artifact(path: Path, snapshot: ArtifactSnapshot) -> None:
    """Put a captured artifact back, or delete it when it did not exist."""
    if snapshot.existed:
        if snapshot.content is None or snapshot.mode is None:
            raise OSError(f"Incomplete snapshot for {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        prior_mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else None
        if prior_mode is not None:
            path.chmod(prior_mode | stat.S_IWRITE)
        try:
            path.write_bytes(snapshot.content)
        except OSError:
            if prior_mode is not None:
                path.chmod(prior_mode)
            raise
        path.chmod(snapshot.mode)
        return
    if path.exists():
        path.unlink()


def missing_directories(directory: Path) -> tuple[Path, ...]:
    """List the directories (deepest first) a write below ``directory`` would create."""
    missing: list[Path] = []
    current = directory
    while not current.exists():
        missing.append(current)
        current = current.parent
    return tuple(missing)


def remove_empty_directories(directories: tuple[Path, ...]) -> int:
    """Remove transaction-created directories that are now empty; 1 on failure."""
    status = 0
    for directory in directories:
        try:
            directory.rmdir()
        except FileNotFoundError:
            continue
        except OSError:
            status = 1
    return status


def unsafe_anchor_issue(anchor: Path) -> str | None:
    """Describe why a project config directory is unsafe for native writes, if so.

    Native managers write their settings below this directory, so a symlink
    (or non-directory) would redirect those writes outside the project.
    """
    if is_link_or_junction(anchor):
        return f"Refusing to use a symlinked or junctioned project config directory: {anchor}"
    if anchor.exists() and not anchor.is_dir():
        return f"Refusing to use a non-directory project config path: {anchor}"
    return None
