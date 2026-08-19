"""Lint execution plan: full inventory, dirty set, and collector families."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from slopgate.config._repo import is_repo_enrolled
from slopgate.lint.catalog import (
    CatalogSurface,
    IMMEDIATE_DUPLICATION_COLLECTORS,
    collector_catalog,
)
from slopgate.lint.project_index.dirty import collect_dirty_and_deleted


@dataclass(frozen=True, slots=True)
class LintPlanRequest:
    """Inputs that distinguish CLI, hook, and integrity lint surfaces."""

    surface: CatalogSurface
    event: str | None
    persist_index: bool
    use_index: bool
    rebuild_index: bool
    build_constants: bool
    active_ids: frozenset[str]
    project_root: Path


@dataclass(frozen=True, slots=True)
class LintExecutionPlan:
    """Incremental execution plan with full-semantic lint check results."""

    src_files: tuple[Path, ...]
    test_files: tuple[Path, ...]
    dirty_paths: tuple[Path, ...]
    deleted_paths: tuple[Path, ...]
    active_ids: frozenset[str]
    file_local_ids: frozenset[str]
    aggregate_ids: frozenset[str]
    persist_index: bool
    use_index: bool
    rebuild_index: bool
    build_constants: bool
    surface: CatalogSurface
    event: str | None
    project_root: Path
    cache_ready: bool = False
    required_fact_types: frozenset[str] = frozenset()
    file_tasks: tuple[str, ...] = ()
    aggregate_tasks: tuple[str, ...] = ()
    git_base_task: bool = False


def build_lint_plan(
    src_files: list[Path],
    test_files: list[Path],
    request: LintPlanRequest,
) -> LintExecutionPlan:
    """Build a plan that keeps full lint semantics with incremental execution."""
    inventory = tuple(path.resolve() for path in [*src_files, *test_files])
    enrolled = is_repo_enrolled(request.project_root)
    persist = request.persist_index and request.use_index and enrolled
    dirty_paths, deleted_paths = collect_dirty_and_deleted(
        request.project_root, inventory
    )
    catalog = collector_catalog()
    file_local = frozenset(
        collector_id
        for collector_id in request.active_ids
        if collector_id in catalog
        and catalog[collector_id].scope == "file"
        and collector_id not in IMMEDIATE_DUPLICATION_COLLECTORS
    )
    aggregate = request.active_ids - file_local
    return LintExecutionPlan(
        src_files=tuple(src_files),
        test_files=tuple(test_files),
        dirty_paths=dirty_paths,
        deleted_paths=deleted_paths,
        active_ids=request.active_ids,
        file_local_ids=file_local,
        aggregate_ids=aggregate,
        persist_index=persist,
        use_index=request.use_index and enrolled,
        rebuild_index=request.rebuild_index,
        build_constants=request.build_constants,
        surface=request.surface,
        event=request.event,
        project_root=request.project_root,
        cache_ready=False,
        required_fact_types=fact_types_for_collectors(request.active_ids),
        file_tasks=tuple(sorted(file_local)),
        aggregate_tasks=tuple(sorted(aggregate)),
        git_base_task=request.surface == "cli",
    )


def fact_types_for_collectors(active_ids: frozenset[str]) -> frozenset[str]:
    """Return persisted fact families required by the active collector set."""
    from slopgate.lint._collector_groups.constants import (
        DEFERRED_TEST_INTEGRITY_COLLECTORS,
    )
    from slopgate.lint.project_index.facts import (
        FACT_TYPE_BLOCKS,
        FACT_TYPE_CALLS,
        FACT_TYPE_CLONES,
        FACT_TYPE_INTEGRITY,
        FACT_TYPE_LITERALS,
    )

    kinds: set[str] = set()
    if "semantic-clone" in active_ids:
        kinds.add(FACT_TYPE_CLONES)
    if "repeated-code-block" in active_ids:
        kinds.add(FACT_TYPE_BLOCKS)
    if "duplicate-call-sequence" in active_ids:
        kinds.add(FACT_TYPE_CALLS)
    if not active_ids.isdisjoint({"repeated-magic-number", "repeated-string-literal"}):
        kinds.add(FACT_TYPE_LITERALS)
    if not active_ids.isdisjoint(DEFERRED_TEST_INTEGRITY_COLLECTORS):
        kinds.add(FACT_TYPE_INTEGRITY)
    return frozenset(kinds)


def apply_index_peek(plan: LintExecutionPlan) -> LintExecutionPlan:
    """Replace git dirty with index-stat dirty when the enrolled cache is warm."""
    if not plan.use_index or plan.rebuild_index:
        return plan
    from slopgate.lint.project_index.peek import peek_index

    peek = peek_index(plan.project_root, (*plan.src_files, *plan.test_files))
    if not peek.ready:
        return plan
    return replace(
        plan,
        dirty_paths=peek.stat_dirty,
        cache_ready=True,
    )
