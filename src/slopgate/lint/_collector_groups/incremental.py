"""Incremental file-local collector execution against persisted violations."""

from __future__ import annotations

from dataclasses import dataclass, replace

from slopgate.lint._baseline import Violation
from slopgate.lint._collector_groups.planner import LintExecutionPlan
from slopgate.lint._helpers import ParsedFile
from slopgate.lint.project_index.models import ProjectIndex
from slopgate.lint.project_index.summarize import dirty_relative_paths


@dataclass(frozen=True, slots=True)
class IncrementalContext:
    """Index-backed incremental execution state for one lint run."""

    plan: LintExecutionPlan
    project_index: ProjectIndex
    cache_ready: bool


def incremental_context(
    plan: LintExecutionPlan, project_index: ProjectIndex
) -> IncrementalContext:
    """Load cache readiness without opening a store when indexing is off."""
    if not plan.use_index:
        return IncrementalContext(plan, project_index, False)
    if plan.cache_ready:
        return IncrementalContext(plan, project_index, True)
    from slopgate.lint.project_index.store import connect_index
    from slopgate.lint.project_index.store import is_file_local_ready
    from slopgate.lint.project_index.store import store_matches_engine

    connection = connect_index(plan.project_root)
    try:
        ready = store_matches_engine(connection, plan.project_root)
        ready = ready and is_file_local_ready(connection)
    finally:
        connection.close()
    return IncrementalContext(plan, project_index, ready)


def plan_with_index_dirty(
    plan: LintExecutionPlan, project_index: ProjectIndex
) -> LintExecutionPlan:
    """Union git dirty paths with content-hash invalidations from the index."""
    extra = tuple(
        (project_index.root / relative).resolve()
        for relative in project_index.dirty_paths
    )
    return replace(plan, dirty_paths=tuple(sorted({*plan.dirty_paths, *extra})))


def restrict_parsed(
    parsed: list[ParsedFile], context: IncrementalContext
) -> list[ParsedFile]:
    """Limit file-local detectors to dirty files when the violation cache is ready."""
    if not context.cache_ready:
        return parsed
    dirty = {path.resolve() for path in context.plan.dirty_paths}
    if not dirty:
        return []
    return [item for item in parsed if item.path.resolve() in dirty]


def restrict_violations(
    items: list[Violation], context: IncrementalContext
) -> list[Violation]:
    """Keep precomputed file-local hits aligned with the dirty set."""
    if not context.cache_ready:
        return items
    dirty = dirty_relatives(context)
    if not dirty:
        return []
    return [item for item in items if item.relative_path in dirty]


def dirty_relatives(context: IncrementalContext) -> set[str]:
    """Return plan dirty paths as POSIX paths relative to the project root."""
    return set(
        dirty_relative_paths(context.plan.project_root, context.plan.dirty_paths)
    )
