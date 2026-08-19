"""Persist and merge cached file-local lint violations."""

from __future__ import annotations

import hashlib
import json
import sqlite3

from dataclasses import replace
from io import DEFAULT_BUFFER_SIZE
from pathlib import Path
from time import perf_counter

from slopgate._types import object_list
from slopgate.lint._baseline import Violation
from slopgate.lint._collector_groups.incremental import IncrementalContext, dirty_relatives
from slopgate.lint._collector_groups.planner import LintExecutionPlan
from slopgate.lint._collector_groups.types import CollectorResults
from slopgate.lint._helpers.profile import LintProfile
from slopgate.lint.project_index.store import (
    connect_index,
    load_cached_collector_results,
    meta_value,
    load_violations_for_hashes,
    mark_file_local_ready,
    replace_file_violations,
)
from slopgate.lint._detectors.test_smells import (
    COVERAGE_JSON_NAMES,
    COVERAGE_XML_NAMES,
)

_COVERAGE_COLLECTOR_ID = "untested-production-code"
_META_COLLECTOR_DEPENDENCY_PREFIX = "collector_dependency:"
_META_COLLECTOR_ORDER = "collector_order"


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
            _persist_collector_order(connection, results)
            _persist_dependency_signatures(connection, context.plan)
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
        if not _dependencies_match(connection, plan):
            return None
        cached = dict(load_cached_collector_results(connection, plan.active_ids))
        return [
            (collector_id, cached[collector_id])
            for collector_id in _cached_collector_order(connection, plan.active_ids)
        ]
    finally:
        connection.close()


def attach_dependency_signatures(plan: LintExecutionPlan) -> LintExecutionPlan:
    """Capture external-input signatures once before collector execution."""
    signatures = tuple(_current_dependency_signatures(plan).items())
    return replace(plan, dependency_signatures=signatures)


def _current_dependency_signatures(plan: LintExecutionPlan) -> dict[str, str]:
    """Return current external-input signatures for active aggregate collectors."""
    if _COVERAGE_COLLECTOR_ID not in plan.active_ids:
        return {}
    return {
        _COVERAGE_COLLECTOR_ID: _coverage_dependency_signature(plan.project_root)
    }


def _dependencies_match(
    connection: sqlite3.Connection, plan: LintExecutionPlan
) -> bool:
    for collector_id, signature in plan.dependency_signatures:
        if meta_value(
            connection, _META_COLLECTOR_DEPENDENCY_PREFIX + collector_id
        ) != signature:
            return False
    return True


def _persist_dependency_signatures(
    connection: sqlite3.Connection, plan: LintExecutionPlan
) -> None:
    for collector_id, signature in plan.dependency_signatures:
        connection.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
            (_META_COLLECTOR_DEPENDENCY_PREFIX + collector_id, signature),
        )


def _coverage_dependency_signature(root: Path) -> str:
    """Hash coverage artifacts consumed by the production-coverage detector."""
    digest = hashlib.sha256()
    for name in (*COVERAGE_JSON_NAMES, *COVERAGE_XML_NAMES):
        path = root / name
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        if not path.is_file():
            digest.update(b"<missing>")
            digest.update(b"\0")
            continue
        try:
            with path.open("rb") as stream:
                while chunk := stream.read(DEFAULT_BUFFER_SIZE):
                    digest.update(chunk)
        except OSError as exc:
            digest.update(f"<unreadable:{type(exc).__name__}>".encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()


def _persist_collector_order(
    connection: sqlite3.Connection, results: CollectorResults
) -> None:
    collector_ids = list(dict.fromkeys(collector_id for collector_id, _ in results))
    connection.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
        (_META_COLLECTOR_ORDER, json.dumps(collector_ids)),
    )


def _cached_collector_order(
    connection: sqlite3.Connection, active_ids: frozenset[str]
) -> tuple[str, ...]:
    row = connection.execute(
        "SELECT value FROM meta WHERE key = ?", (_META_COLLECTOR_ORDER,)
    ).fetchone()
    if row is None:
        return tuple(sorted(active_ids))
    try:
        stored = object_list(json.loads(str(row["value"])))
    except json.JSONDecodeError:
        return tuple(sorted(active_ids))
    ordered = tuple(
        dict.fromkeys(
            item for item in stored if isinstance(item, str) and item in active_ids
        )
    )
    return (*ordered, *sorted(active_ids - set(ordered)))


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
