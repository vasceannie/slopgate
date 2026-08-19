"""Enrolled-repo incremental SQLite project index builds."""

from __future__ import annotations

from dataclasses import replace

from slopgate.lint.project_index.models import ProjectIndex, ProjectIndexRequest
from slopgate.lint.project_index.store import (
    connect_index,
    reset_store,
    store_matches_engine,
)
from slopgate.lint.project_index.summarize import (
    index_root,
    sorted_project_paths,
    summary_payload_size,
)


def build_persisted_index(request: ProjectIndexRequest) -> ProjectIndex:
    """Load, invalidate dirty/deleted rows, and persist updated file facts."""
    project_paths = sorted_project_paths(request.src_files, request.test_files)
    root = index_root(request.root, tuple(path for path, _ in project_paths))
    connection = connect_index(root)
    try:
        if request.rebuild or not store_matches_engine(connection, root):
            reset_store(connection, root)
        from slopgate.lint.project_index.refresh import refresh_index_summaries

        summaries, refreshed = refresh_index_summaries(
            connection, root, request, project_paths
        )
        request = replace(
            request, dirty_paths=tuple(sorted({*request.dirty_paths, *refreshed}))
        )
        bytes_used = sum(summary_payload_size(summary) for summary in summaries)
        index = ProjectIndex.from_summaries(root, request, summaries, bytes_used)
        from slopgate.lint.project_index.integrity_store import save_integrity_index

        save_integrity_index(connection, index)
        connection.commit()
        return index
    finally:
        connection.close()
