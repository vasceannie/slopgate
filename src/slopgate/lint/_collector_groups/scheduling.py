"""Collector spec scheduling: resolve enablement before detector execution."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from slopgate.constants import LINT_PARALLEL_MIN_COLLECTORS

from slopgate.lint._baseline import Violation
from slopgate.lint._collector_groups.enablement import collector_enabled
from slopgate.lint._collector_groups.types import CollectorResults
from slopgate.lint._helpers import relative_path
from slopgate.lint._helpers.models import FileParseAttempt, FileParseError, PARSE_ERROR_KIND_READ
from slopgate.lint._helpers.profile import LintProfile
from slopgate.lint.catalog import (
    CatalogEntry,
    CatalogSurface,
    collector_catalog,
    collector_ids_for_surface,
    filter_cataloged_collectors,
)


@dataclass(frozen=True, slots=True)
class CollectorSpec:
    """Deferred collector invocation scheduled after enablement resolution."""

    collector_id: str
    run: Callable[[], list[Violation]]


def active_collector_ids(
    surface: CatalogSurface, *, event: str | None = None
) -> frozenset[str]:
    """Return catalog collector IDs that should execute on *surface*."""
    from slopgate.lint._config import get_config

    enabled_cli_rules = get_config().enabled_cli_rules
    return frozenset(
        collector_id
        for collector_id in collector_ids_for_surface(surface, event=event)
        if collector_enabled(collector_id, enabled_cli_rules)
    )


def spec_is_scheduled(
    spec: CollectorSpec,
    *,
    catalog: dict[str, CatalogEntry],
    allowed: frozenset[str],
    enabled_cli_rules: dict[str, bool],
) -> bool:
    """Return True when *spec* should run for the resolved surface and config."""
    if spec.collector_id in catalog and spec.collector_id not in allowed:
        return False
    return collector_enabled(spec.collector_id, enabled_cli_rules)


def execute_specs(
    specs: Sequence[CollectorSpec],
    surface: CatalogSurface,
    *,
    event: str | None = None,
    profile: LintProfile | None = None,
) -> CollectorResults:
    """Run enabled specs and keep unknown IDs as a catalog safety net."""
    from slopgate.lint._config import get_config

    enabled_cli_rules = get_config().enabled_cli_rules
    catalog = collector_catalog()
    allowed = collector_ids_for_surface(surface, event=event)
    scheduled = [
        spec
        for spec in specs
        if spec_is_scheduled(
            spec,
            catalog=catalog,
            allowed=allowed,
            enabled_cli_rules=enabled_cli_rules,
        )
    ]
    results = _execute_scheduled(scheduled, catalog, profile)
    return filter_cataloged_collectors(results, surface, event=event)


def execute_all(specs: Sequence[CollectorSpec]) -> CollectorResults:
    """Run every spec without enablement filtering (catalog-shape tests)."""
    return [(spec.collector_id, spec.run()) for spec in specs]


def _parse_error_violation(path: Path, error: FileParseError) -> Violation:
    if error.kind == PARSE_ERROR_KIND_READ:
        return Violation(
            rule="python-parse-error",
            relative_path=relative_path(path),
            identifier="read-error",
            detail=error.message,
        )
    return Violation(
        rule="python-parse-error",
        relative_path=relative_path(path),
        identifier=f"line-{error.line}",
        detail=error.message,
        metadata={tuple(FileParseError.__dataclass_fields__)[2]: error.line, "offset": error.offset},
    )


def parse_error_violations(attempts: Sequence[FileParseAttempt]) -> list[Violation]:
    """Map retained parse attempts to baseline-able parse-error violations."""
    return [
        _parse_error_violation(attempt.path, attempt.error)
        for attempt in attempts
        if attempt.error is not None
    ]


def parse_error_spec(attempts: Sequence[FileParseAttempt]) -> CollectorSpec:
    """Build a deferred python-parse-error collector from one parse pass."""
    return CollectorSpec(
        "python-parse-error",
        lambda: parse_error_violations(attempts),
    )


def _cheap_file_spec(spec: CollectorSpec, catalog: dict[str, CatalogEntry]) -> bool:
    entry = catalog.get(spec.collector_id)
    return entry is not None and entry.scope == "file" and entry.cost == "cheap"


def _run_timed_spec(spec: CollectorSpec) -> tuple[str, list[Violation], float]:
    started = perf_counter()
    violations = spec.run()
    return spec.collector_id, violations, perf_counter() - started


def _record_timed(
    timed: Sequence[tuple[str, list[Violation], float]],
    profile: LintProfile | None,
) -> CollectorResults:
    results: CollectorResults = []
    for collector_id, violations, seconds in timed:
        if profile is not None:
            profile.record_collector(collector_id, seconds)
        results.append((collector_id, violations))
    return results


def _run_specs_parallel(
    specs: Sequence[CollectorSpec], profile: LintProfile | None
) -> CollectorResults:
    with ThreadPoolExecutor() as pool:
        timed = list(pool.map(_run_timed_spec, specs))
    return _record_timed(timed, profile)


def _execute_scheduled(
    scheduled: Sequence[CollectorSpec],
    catalog: dict[str, CatalogEntry],
    profile: LintProfile | None,
) -> CollectorResults:
    cheap = [spec for spec in scheduled if _cheap_file_spec(spec, catalog)]
    rest = [spec for spec in scheduled if not _cheap_file_spec(spec, catalog)]
    cheap_indexes = [
        index for index, spec in enumerate(scheduled) if _cheap_file_spec(spec, catalog)
    ]
    rest_indexes = [
        index
        for index, spec in enumerate(scheduled)
        if not _cheap_file_spec(spec, catalog)
    ]
    cheap_run = (
        _run_specs_parallel(cheap, profile)
        if len(cheap) >= LINT_PARALLEL_MIN_COLLECTORS
        else _record_timed([_run_timed_spec(spec) for spec in cheap], profile)
    )
    rest_run = _record_timed([_run_timed_spec(spec) for spec in rest], profile)
    ordered = dict(zip(cheap_indexes, cheap_run, strict=True))
    ordered.update(zip(rest_indexes, rest_run, strict=True))
    return [ordered[index] for index in range(len(scheduled))]


__all__ = [
    "CollectorSpec",
    "active_collector_ids",
    "execute_all",
    "execute_specs",
    "parse_error_spec",
    "parse_error_violations",
    "spec_is_scheduled",
]
