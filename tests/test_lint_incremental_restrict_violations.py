"""Contract for restrict_violations passthrough on a cold cache."""

from __future__ import annotations

from pathlib import Path

from slopgate.lint._collector_groups.incremental import (
    IncrementalContext,
    restrict_violations,
)
from slopgate.lint._collector_groups.planner import LintExecutionPlan
from slopgate.lint.project_index.models import ProjectIndex, ProjectIndexRequest


def cold_index_context(root: Path) -> IncrementalContext:
    if not root.is_absolute():
        raise ValueError("root must be absolute")
    plan = LintExecutionPlan(
        src_files=(),
        test_files=(),
        dirty_paths=(),
        deleted_paths=(),
        active_ids=frozenset(),
        file_local_ids=frozenset(),
        aggregate_ids=frozenset(),
        persist_index=False,
        use_index=False,
        rebuild_index=False,
        build_constants=False,
        surface="cli",
        event=None,
        project_root=root,
        cache_ready=False,
    )
    index = ProjectIndex.from_summaries(
        root,
        ProjectIndexRequest(root=root, src_files=(), test_files=()),
        (),
        0,
    )
    return IncrementalContext(plan, index, False)


def test_restrict_violations_passthrough_when_cache_cold(tmp_path: Path) -> None:
    assert restrict_violations([], cold_index_context(tmp_path)) == []
