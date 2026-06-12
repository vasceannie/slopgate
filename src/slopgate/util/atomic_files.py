"""Shared locked file write helpers."""

from __future__ import annotations

import os
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TextIO

from slopgate.state._models import fcntl

_PATH_LOCK_GUARD = threading.Lock()
_PATH_LOCKS: dict[Path, threading.Lock] = {}


def append_lines_locked(path: Path, lines: list[str]) -> None:
    """Append lines while holding process-local and OS file locks."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with locked_path(path):
        with path.open("a", encoding="utf-8") as handle:
            handle.writelines(lines)


def write_text_atomic_locked(
    path: Path,
    text: str,
    *,
    prefix: str,
    suffix: str,
) -> None:
    """Atomically replace path contents while holding per-path locks."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with locked_path(path):
        tmp_name = _write_temp_text(path.parent, text, prefix=prefix, suffix=suffix)
        try:
            os.replace(tmp_name, path)
        finally:
            _remove_temp_file(tmp_name)


@contextmanager
def locked_path(path: Path) -> Iterator[None]:
    """Lock a logical path across threads and cooperating processes."""

    lock = _path_lock_for(path)
    with lock:
        lock_path = path.with_suffix(path.suffix + ".lock")
        with lock_path.open("a+", encoding="utf-8") as handle:
            with _locked_file(handle):
                yield


def _path_lock_for(path: Path) -> threading.Lock:
    with _PATH_LOCK_GUARD:
        lock = _PATH_LOCKS.get(path)
        if lock is None:
            lock = threading.Lock()
            _PATH_LOCKS[path] = lock
        return lock


@contextmanager
def _locked_file(handle: TextIO) -> Iterator[None]:
    if fcntl is not None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    try:
        yield
    finally:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _write_temp_text(parent: Path, text: str, *, prefix: str, suffix: str) -> str:
    fd, tmp_name = tempfile.mkstemp(prefix=prefix, suffix=suffix, dir=str(parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            _ = handle.write(text)
    except OSError:
        _remove_temp_file(tmp_name)
        raise
    return tmp_name


def _remove_temp_file(path: str) -> None:
    if not os.path.exists(path):
        return
    try:
        os.unlink(path)
    except OSError:
        return
