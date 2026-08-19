"""Persist and merge cached file-local lint violations."""

from __future__ import annotations

import sqlite3

from time import perf_counter

from slopgate.lint._baseline import Violation
from slopgate.lint._collector_groups.incremental import IncrementalContext, dirty_relatives
from slopgate.lint._collector_groups.planner import LintExecutionPlan
from slopgate.lint._collector_groups.types import CollectorResults
from slopgate.lint._helpers.profile import LintProfile
from slopgate.lint.project_index.store import (
    connect_index,
    load_cached_collector_results,
    load_violations_for_hashes,
    mark_file_local_ready,
    replace_file_violations,
)


def complete_incremental_results(
    results: CollectorResults, context: IncrementalContext
) -> CollectorResults:
    """Merge cached file-local hits and persist newly computed dirty-file facts."""
    if not context.plan.use_index:
        return results
    connection = connect_index(context.plan.project_root)
    try:
        merged = results
        if context.cache_ready:
            merged = _merge_cached(connection, results, context)
        if context.plan.persist_index:
            _persist_live(connection, results, context)
            mark_file_local_ready(connection)
            connection.commit()
        return merged
    finally:
        connection.close()


def persist_run_results(
    results: CollectorResults,
    context: IncrementalContext,
    profile: LintProfile | None,
) -> CollectorResults:
    """Persist incremental results and record the persist phase when profiled."""
    started = perf_counter()
    merged = complete_incremental_results(results, context)
    if profile is not None:
        profile.record_phase("persist", perf_counter() - started)
    return merged


def cached_run_results(plan: LintExecutionPlan) -> CollectorResults | None:
    """Return a full cached result set when the tree is clean and the index is ready."""
    if not plan.cache_ready or plan.dirty_paths or plan.deleted_paths:
        return None
    connection = connect_index(plan.project_root)
    try:
        return load_cached_collector_results(connection, plan.active_ids)
    finally:
        connection.close()


def _clean_relatives(context: IncrementalContext) -> tuple[str, ...]:
    dirty = dirty_relatives(context)
    return tuple(
        summary.relative_path
        for summary in context.project_index.files
        if summary.relative_path not in dirty
    )


def _refresh_hashes(context: IncrementalContext) -> dict[str, str]:
    dirty = dirty_relatives(context)
    if not context.cache_ready:
        return {
            summary.relative_path: summary.content_hash
            for summary in context.project_index.files
        }
    return {
        summary.relative_path: summary.content_hash
        for summary in context.project_index.files
        if summary.relative_path in dirty
    }


def _merge_cached(
    connection: sqlite3.Connection,
    results: CollectorResults,
    context: IncrementalContext,
) -> CollectorResults:
    relatives = _clean_relatives(context)
    merged: CollectorResults = []
    for collector_id, violations in results:
        if collector_id not in context.plan.file_local_ids:
            merged.append((collector_id, violations))
            continue
        cached = load_violations_for_hashes(connection, collector_id, relatives)
        merged.append((collector_id, [*violations, *cached]))
    return merged


def _persist_live(
    connection: sqlite3.Connection,
    results: CollectorResults,
    context: IncrementalContext,
) -> None:
    hashes = _refresh_hashes(context)
    live = {collector_id: violations for collector_id, violations in results}
    for collector_id in context.plan.file_local_ids:
        grouped = _group_by_relative(live.get(collector_id, ()))
        for relative, content_hash in hashes.items():
            replace_file_violations(
                connection,
                collector_id,
                (content_hash, relative),
                grouped.get(relative, ()),
            )
    for collector_id in context.plan.aggregate_ids:
        replace_file_violations(
            connection,
            collector_id,
            None,
            live.get(collector_id, ()),
        )


def _group_by_relative(
    violations: tuple[Violation, ...] | list[Violation],
) -> dict[str, list[Violation]]:
    grouped: dict[str, list[Violation]] = {}
    for violation in violations:
        grouped.setdefault(violation.relative_path, []).append(violation)
    return grouped
