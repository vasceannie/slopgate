"""Integration contracts for serialized lint-index writers."""

from __future__ import annotations

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from slopgate.lint.project_index import refresh
from slopgate.lint.project_index.models import (
    ProjectFileSummary,
    ProjectIndex,
    ProjectIndexRequest,
)
from slopgate.lint.project_index.persist import build_persisted_index
from slopgate.lint.project_index.store import index_db_path
from slopgate.lint.project_index.write_lock import locked_index_connection


def _request(root: Path) -> ProjectIndexRequest:
    source = root / "src/pkg.py"
    source.parent.mkdir(parents=True)
    source.write_text("VALUE = 1\n", encoding="utf-8")
    return ProjectIndexRequest(root, (source,), (), persist=True, use_store=True)


def _run_concurrent_builds(
    request: ProjectIndexRequest, monkeypatch: pytest.MonkeyPatch
) -> tuple[bool, ProjectIndex, ProjectIndex]:
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

    def marked_build() -> ProjectIndex:
        second_started.set()
        return build_persisted_index(request)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(build_persisted_index, request)
        assert first_entered.wait(timeout=1), "first writer should reach refresh"
        second = executor.submit(marked_build)
        assert second_started.wait(timeout=1), "second writer should start"
        overlapped = second_entered.wait(timeout=0.25)
        release_first.set()
        return overlapped, first.result(timeout=2), second.result(timeout=2)


def test_locked_index_connection_opens_project_store(tmp_path: Path) -> None:
    with locked_index_connection(tmp_path) as connection:
        database = Path(str(connection.execute("PRAGMA database_list").fetchone()[2]))
    assert database == index_db_path(tmp_path), "writer lock should guard the project store"


def test_build_persisted_index_serializes_concurrent_writers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request(tmp_path)
    build_persisted_index(request)
    overlapped, first_index, second_index = _run_concurrent_builds(request, monkeypatch)
    assert not overlapped, "persisted index writers must not overlap"
    assert first_index.files == second_index.files, "serialized builds should agree"
