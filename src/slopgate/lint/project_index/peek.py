"""Cheap index peek: cache readiness and stat-dirty paths without parsing."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from slopgate.lint.project_index.store import (
    connect_index,
    is_file_local_ready,
    load_file_rows,
    store_matches_engine,
)


@dataclass(frozen=True, slots=True)
class IndexPeek:
    """Pre-parse view of the enrolled lint index."""

    ready: bool
    stat_dirty: tuple[Path, ...]


def peek_index(root: Path, inventory: tuple[Path, ...]) -> IndexPeek:
    """Return whether file-local facts are ready and which paths fail a stat check."""
    connection = connect_index(root)
    try:
        ready = store_matches_engine(connection, root) and is_file_local_ready(
            connection
        )
        stored = load_file_rows(connection) if ready else {}
    finally:
        connection.close()
    if not ready:
        return IndexPeek(False, ())
    return IndexPeek(True, _stat_mismatched(root, inventory, stored))


def _stat_mismatched(
    root: Path,
    inventory: tuple[Path, ...],
    stored: dict[str, sqlite3.Row],
) -> tuple[Path, ...]:
    dirty: list[Path] = []
    for path in inventory:
        resolved = path.resolve()
        if not resolved.is_relative_to(root):
            continue
        relative = resolved.relative_to(root).as_posix()
        row = stored.get(relative)
        if row is None or not _row_current(resolved, row):
            dirty.append(resolved)
    return tuple(sorted(dirty))


def _row_current(path: Path, row: sqlite3.Row) -> bool:
    return _row_stat_matches(path, row) or _row_content_matches(path, row)


def _row_stat_matches(path: Path, row: sqlite3.Row) -> bool:
    try:
        stat = path.stat()
    except OSError:
        return False
    return int(row["mtime_ns"]) == stat.st_mtime_ns and int(row["size"]) == stat.st_size


def _row_content_matches(path: Path, row: sqlite3.Row) -> bool:
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    if digest != str(row["content_hash"]):
        return False
    stripped = filter(None, (line.strip() for line in source.splitlines()))
    fingerprint = hashlib.sha256("\n".join(stripped).encode("utf-8")).hexdigest()
    return fingerprint == str(row["duplicate_fingerprint"])
