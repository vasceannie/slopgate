"""Refresh persisted file summaries for dirty and missing paths."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from slopgate.lint._helpers.models import FileParseAttempt
from slopgate.lint.project_index.models import ProjectFileSummary, ProjectIndexRequest
from slopgate.lint.project_index.store import (
    delete_files,
    load_file_rows,
    summary_from_row,
    upsert_file,
)
from slopgate.lint.project_index.fact_filter import fact_type_filter
from slopgate.lint.project_index.summarize import attempt_lookup, summarize_project_file


def refresh_index_summaries(
    connection: sqlite3.Connection,
    root: Path,
    request: ProjectIndexRequest,
    project_paths: tuple[tuple[Path, str], ...],
) -> tuple[tuple[ProjectFileSummary, ...], tuple[Path, ...]]:
    """Reanalyze stale files and reuse stored facts for unchanged content."""
    stored = load_file_rows(connection)
    delete_files(connection, _dropped_relatives(root, project_paths, stored))
    attempts_by_path = attempt_lookup(request.attempts)
    summaries: list[ProjectFileSummary] = []
    refreshed: list[Path] = []
    for path, kind in project_paths:
        resolved = path.resolve()
        relative = resolved.relative_to(root).as_posix()
        if relative in stored and _stored_row_matches(
            resolved, stored[relative], attempts_by_path
        ):
            summaries.append(summary_from_row(root, stored[relative]))
            continue
        with fact_type_filter(request.fact_types):
            summary = summarize_project_file(root, path, kind, attempts_by_path)
        if summary is None:
            continue
        upsert_file(connection, summary)
        summaries.append(summary)
        refreshed.append(resolved)
    return tuple(summaries), tuple(sorted(refreshed))


def _stored_row_matches(
    path: Path,
    row: sqlite3.Row,
    attempts_by_path: dict[Path, FileParseAttempt],
) -> bool:
    attempt = attempts_by_path.get(path)
    if attempt is not None:
        return str(row["content_hash"]) == attempt.content_hash
    try:
        stat = path.stat()
    except OSError:
        return False
    return int(row["mtime_ns"]) == stat.st_mtime_ns and int(row["size"]) == stat.st_size


def _dropped_relatives(
    root: Path,
    project_paths: tuple[tuple[Path, str], ...],
    stored: dict[str, sqlite3.Row],
) -> tuple[str, ...]:
    current = {
        path.resolve().relative_to(root).as_posix()
        for path, _kind in project_paths
        if path.resolve().is_relative_to(root)
    }
    return tuple(relative for relative in stored if relative not in current)
