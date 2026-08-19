"""Build in-memory or enrolled SQLite project indexes."""

from __future__ import annotations

from slopgate.config._repo import is_repo_enrolled
from slopgate.lint.project_index.models import (
    ProjectFileSummary,
    ProjectIndex,
    ProjectIndexRequest,
)
from slopgate.lint.project_index.summarize import (
    attempt_lookup,
    index_root,
    sorted_project_paths,
    summarize_project_file,
    summary_payload_size,
)


def build_project_index(request: ProjectIndexRequest) -> ProjectIndex:
    """Build a sorted, compact, deterministic project metadata index."""
    if request.persist and request.use_store and is_repo_enrolled(request.root):
        from slopgate.lint.project_index.persist import build_persisted_index

        return build_persisted_index(request)
    return _build_memory_index(request)


def _build_memory_index(request: ProjectIndexRequest) -> ProjectIndex:
    project_paths = sorted_project_paths(request.src_files, request.test_files)
    root = index_root(request.root, tuple(path for path, _ in project_paths))
    attempts_by_path = attempt_lookup(request.attempts)
    summaries: list[ProjectFileSummary] = []
    bytes_used = 0
    for path, kind in project_paths:
        summary = summarize_project_file(root, path, kind, attempts_by_path)
        if summary is None:
            continue
        payload_size = summary_payload_size(summary)
        if bytes_used + payload_size > request.max_bytes:
            continue
        summaries.append(summary)
        bytes_used += payload_size
    return ProjectIndex.from_summaries(root, request, tuple(summaries), bytes_used)
