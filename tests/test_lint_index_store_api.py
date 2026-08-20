"""Contract for enrolled lint index database path."""

from __future__ import annotations

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from slopgate.constants import LINT_CACHE_DIRNAME, LINT_INDEX_FILENAME
from slopgate.lint.project_index import refresh
from slopgate.lint.project_index.models import ProjectFileSummary, ProjectIndexRequest
from slopgate.lint.project_index.persist import build_persisted_index
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


def test_build_persisted_index_serializes_concurrent_writers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "src/pkg.py"
    source.parent.mkdir(parents=True)
    source.write_text("VALUE = 1\n", encoding="utf-8")
    request = ProjectIndexRequest(tmp_path, (source,), (), persist=True, use_store=True)
    build_persisted_index(request)
    original_refresh = refresh.refresh_index_summaries
    first_entered = threading.Event()
    release_first = threading.Event()
    second_started = threading.Event()
    second_entered = threading.Event()
    call_lock = threading.Lock()
    calls: list[None] = []

    def gated_refresh(
        connection: sqlite3.Connection,
        root: Path,
        current_request: ProjectIndexRequest,
        project_paths: tuple[tuple[Path, str], ...],
    ) -> tuple[tuple[ProjectFileSummary, ...], tuple[Path, ...]]:
        with call_lock:
            calls.append(None)
            first_call = len(calls) == 1
        if first_call:
            first_entered.set()
            release_first.wait(timeout=2)
        else:
            second_entered.set()
        return original_refresh(connection, root, current_request, project_paths)

    monkeypatch.setattr(refresh, "refresh_index_summaries", gated_refresh)

    def marked_build():
        second_started.set()
        return build_persisted_index(request)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(build_persisted_index, request)
        assert first_entered.wait(timeout=1), "first writer should reach refresh"
        second = executor.submit(marked_build)
        assert second_started.wait(timeout=1), "second writer should start"
        overlapped = second_entered.wait(timeout=0.25)
        release_first.set()
        first_index = first.result(timeout=2)
        second_index = second.result(timeout=2)
    assert not overlapped, "persisted index writers must not overlap"
    assert first_index.files == second_index.files, "serialized builds should agree"
