"""Contracts for incremental dirty-path restriction helpers."""

from __future__ import annotations

from pathlib import Path

from slopgate.lint._collector_groups.incremental import (
    IncrementalContext,
    dirty_relatives,
    incremental_context,
    plan_with_index_dirty,
    restrict_parsed,
)
from slopgate.lint._collector_groups.planner import LintExecutionPlan
from slopgate.lint.project_index.models import ProjectIndex, ProjectIndexRequest


def unused_index_context(root: Path) -> IncrementalContext:
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


def test_incremental_context_type(tmp_path: Path) -> None:
    assert unused_index_context(tmp_path).cache_ready is False


def test_dirty_relatives_empty_when_clean(tmp_path: Path) -> None:
    assert dirty_relatives(unused_index_context(tmp_path)) == set()


def test_incremental_context_skips_store_when_index_off(tmp_path: Path) -> None:
    seeded = unused_index_context(tmp_path)
    context = incremental_context(seeded.plan, seeded.project_index)
    assert context.cache_ready is False


def test_plan_with_index_dirty_keeps_empty_union(tmp_path: Path) -> None:
    seeded = unused_index_context(tmp_path)
    updated = plan_with_index_dirty(seeded.plan, seeded.project_index)
    assert updated.dirty_paths == ()


def test_restrict_parsed_passthrough_when_cache_cold(tmp_path: Path) -> None:
    assert restrict_parsed([], unused_index_context(tmp_path)) == []
