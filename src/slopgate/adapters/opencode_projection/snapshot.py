"""Stable filesystem snapshots for projected OpenCode mutations."""

from __future__ import annotations

import hashlib
import errno
import os
from collections.abc import Generator
from contextlib import ExitStack, contextmanager
from pathlib import Path

from .models import Snapshot, SnapshotStatus


@contextmanager
def _closing_descriptor(descriptor: int) -> Generator[int]:
    try:
        yield descriptor
    finally:
        os.close(descriptor)


def _directory_flags() -> int:
    nofollow = getattr(os, "O_NOFOLLOW", None)
    directory = getattr(os, "O_DIRECTORY", None)
    if nofollow is None or directory is None or os.open not in os.supports_dir_fd:
        raise OSError(errno.ENOTSUP, "secure descriptor-relative reads are unavailable")
    return os.O_RDONLY | nofollow | directory


def _open_directory(path: Path) -> int:
    resolved = path.resolve(strict=True)
    flags = _directory_flags()
    with ExitStack() as descriptors:
        current = descriptors.enter_context(
            _closing_descriptor(os.open(resolved.anchor, flags))
        )
        for part in resolved.parts[1:]:
            current = descriptors.enter_context(
                _closing_descriptor(os.open(part, flags, dir_fd=current))
            )
        return os.dup(current)


def _open_relative_file(root: Path, relative: str) -> int:
    parts = Path(relative).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise OSError(errno.EINVAL, "snapshot path must be a non-empty relative path")
    flags = _directory_flags()
    with ExitStack() as descriptors:
        current = descriptors.enter_context(_closing_descriptor(_open_directory(root)))
        for part in parts[:-1]:
            current = descriptors.enter_context(
                _closing_descriptor(os.open(part, flags, dir_fd=current))
            )
        nofollow = getattr(os, "O_NOFOLLOW", 0)
        return os.open(parts[-1], os.O_RDONLY | nofollow, dir_fd=current)


def _identity_key(stat_result: os.stat_result) -> tuple[int, int, int, int]:
    return (
        stat_result.st_dev,
        stat_result.st_ino,
        stat_result.st_size,
        stat_result.st_mtime_ns,
    )


def read_snapshot(root: Path, relative: str) -> Snapshot | SnapshotStatus:
    """Read content only when file identity is stable across the read."""
    try:
        descriptor = _open_relative_file(root, relative)
    except FileNotFoundError:
        return "missing"
    except OSError:
        return "stale"
    try:
        with os.fdopen(descriptor, "rb") as handle:
            before = os.fstat(handle.fileno())
            content = handle.read().decode("utf-8")
            after = os.fstat(handle.fileno())
    except UnicodeError:
        return "invalid"
    except OSError:
        return "stale"
    if _identity_key(before) != _identity_key(after):
        return "stale"
    return Snapshot(
        content=content,
        sha256=hashlib.sha256(content.encode()).hexdigest(),
    )
