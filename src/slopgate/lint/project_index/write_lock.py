"""Serialize enrolled lint-index writers across cooperating processes."""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import closing, contextmanager
from pathlib import Path

from slopgate.lint.project_index.store import connect_index, index_db_path
from slopgate.util.atomic_files import locked_path


@contextmanager
def locked_index_connection(root: Path) -> Generator[sqlite3.Connection]:
    """Yield the lint-index connection while holding its cross-process write lock."""
    path = index_db_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with locked_path(path), closing(connect_index(root)) as connection:
        yield connection
