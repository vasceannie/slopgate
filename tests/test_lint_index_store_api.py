"""Contract for enrolled lint index database path."""

from __future__ import annotations

from pathlib import Path

from slopgate.constants import LINT_CACHE_DIRNAME, LINT_INDEX_FILENAME
from slopgate.lint.project_index.store import (
    connect_index,
    index_db_path,
    is_file_local_ready,
    load_file_rows,
    store_matches_engine,
)


def test_index_db_path_uses_cache_layout(tmp_path: Path) -> None:
    assert index_db_path(tmp_path) == tmp_path / LINT_CACHE_DIRNAME / LINT_INDEX_FILENAME


def test_connect_index_opens_sqlite(tmp_path: Path) -> None:
    connection = connect_index(tmp_path)
    ready = is_file_local_ready(connection)
    matches = store_matches_engine(connection, tmp_path)
    rows = load_file_rows(connection)
    connection.close()
    assert {
        "path": index_db_path(tmp_path).is_file(),
        "ready": ready,
        "matches": matches,
        "rows": rows,
    } == {"path": True, "ready": False, "matches": False, "rows": {}}
