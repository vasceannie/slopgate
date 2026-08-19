"""Cheap contracts for incremental cache and planner public APIs."""

from __future__ import annotations

from pathlib import Path

from slopgate.lint._collector_groups.incremental_cache import (
    cached_run_results,
    complete_incremental_results,
    persist_run_results,
)
from slopgate.lint._collector_groups.planner import (
    LintExecutionPlan,
    LintPlanRequest,
    apply_index_peek,
    build_lint_plan,
)


def _cli_plan(root: Path, dirty: tuple[Path, ...]) -> LintExecutionPlan:
    if not root.is_absolute():
        raise ValueError("plan root must be absolute")
    return LintExecutionPlan(
        src_files=(),
        test_files=(),
        dirty_paths=dirty,
        deleted_paths=(),
        active_ids=frozenset(),
        file_local_ids=frozenset(),
        aggregate_ids=frozenset(),
        persist_index=False,
        use_index=True,
        rebuild_index=False,
        build_constants=False,
        surface="cli",
        event=None,
        project_root=root,
        cache_ready=True,
    )


def test_cached_run_results_skip_when_dirty(tmp_path: Path) -> None:
    plan = _cli_plan(tmp_path, (tmp_path / "src/a.py",))
    assert {
        "cached": cached_run_results(plan),
        "complete": complete_incremental_results.__name__,
        "persist": persist_run_results.__name__,
    } == {
        "cached": None,
        "complete": "complete_incremental_results",
        "persist": "persist_run_results",
    }


def test_apply_index_peek_noop_without_persist(tmp_path: Path) -> None:
    plan = _cli_plan(tmp_path, ())
    assert apply_index_peek(plan) is plan


def test_build_lint_plan_disables_persist_when_unenrolled(tmp_path: Path) -> None:
    request = LintPlanRequest(
        surface="cli",
        event=None,
        persist_index=True,
        use_index=True,
        rebuild_index=False,
        build_constants=False,
        active_ids=frozenset(),
        project_root=tmp_path,
    )
    plan = build_lint_plan([], [], request)
    assert plan.persist_index is False
