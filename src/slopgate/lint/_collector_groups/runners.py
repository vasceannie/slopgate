"""Collector runner implementations."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from slopgate.lint._collector_groups.incremental import (
    incremental_context,
    plan_with_index_dirty,
    restrict_parsed,
    restrict_violations,
)
from slopgate.lint._collector_groups.incremental_cache import (
    cached_run_results,
    persist_run_results,
)
from slopgate.lint._helpers.profile import bind_lint_profile
from slopgate.lint._collector_groups.planner import (
    LintExecutionPlan,
    LintPlanRequest,
    apply_index_peek,
    build_lint_plan,
)
from slopgate.lint._collector_groups.run_options import (
    CollectorRunOptions,
    collector_options_from_env,
)
from slopgate.lint._collector_groups.runner_specs import (
    CollectorSpecInputs,
    cli_collector_specs,
)
from slopgate.lint._collector_groups.scheduling import (
    active_collector_ids,
    execute_specs,
)
from slopgate.lint._collector_groups.source import source_analysis
from slopgate.lint._collector_groups.types import CollectorResults, SourceAnalysisOptions
from slopgate.lint._collector_groups.source_prepare import last_parse_attempts


def run_test_integrity_collectors(
    src_files: list[Path],
    test_files: list[Path],
) -> CollectorResults:
    """Run focused detectors for bad-test-efficacy indicators only."""
    return _run_collectors(
        src_files,
        test_files,
        replace(collector_options_from_env(), surface="cli", integrity_mode="full"),
    )


def run_touched_collectors(
    src_files: list[Path],
    test_files: list[Path],
    *,
    reference_test_files: list[Path] | None = None,
) -> CollectorResults:
    """Run immediate detectors for touched files."""
    del reference_test_files
    return _run_collectors(
        src_files,
        test_files,
        CollectorRunOptions(
            surface="hook",
            event="PostToolUse",
            build_constants=False,
            integrity_mode="touched",
            persist_index=False,
            use_index=False,
        ),
    )


def run_all_collectors(
    src_files: list[Path],
    test_files: list[Path],
    options: CollectorRunOptions | None = None,
) -> CollectorResults:
    """Run all detectors and return (rule_name, violations) pairs."""
    return _run_collectors(
        src_files, test_files, options or collector_options_from_env()
    )


def _run_collectors(
    src_files: list[Path],
    test_files: list[Path],
    options: CollectorRunOptions,
) -> CollectorResults:
    plan = apply_index_peek(_plan_for_options(src_files, test_files, options))
    cached = cached_run_results(plan)
    if cached is not None:
        bind_lint_profile(options.profile)
        return cached
    analysis = source_analysis(
        src_files,
        test_files,
        SourceAnalysisOptions(
            active_ids=plan.active_ids,
            build_constants=plan.build_constants,
            persist_index=plan.persist_index,
            use_index=plan.use_index,
            rebuild_index=plan.rebuild_index,
            profile=options.profile,
            dirty_paths=plan.dirty_paths,
            parse_paths=plan.dirty_paths if plan.cache_ready else None,
            deleted_paths=plan.deleted_paths,
            fact_types=plan.required_fact_types,
        ),
    )
    parsed_src, parsed_tests, oversized, literals, project_index = analysis
    context = incremental_context(
        plan_with_index_dirty(plan, project_index), project_index
    )
    specs = cli_collector_specs(
        CollectorSpecInputs(
            attempts=last_parse_attempts(),
            parsed_src=parsed_src,
            parsed_tests=parsed_tests,
            file_local_src=restrict_parsed(parsed_src, context),
            file_local_tests=restrict_parsed(parsed_tests, context),
            oversized=restrict_violations(oversized, context),
            literals=literals,
            integrity_mode=options.integrity_mode,
            project_index=project_index,
        )
    )
    bind_lint_profile(options.profile)
    results = execute_specs(
        specs, options.surface, event=options.event, profile=options.profile
    )
    return persist_run_results(results, context, options.profile)


def _plan_for_options(
    src_files: list[Path],
    test_files: list[Path],
    options: CollectorRunOptions,
) -> LintExecutionPlan:
    from slopgate.lint._config import get_config

    return build_lint_plan(
        src_files,
        test_files,
        LintPlanRequest(
            surface=options.surface,
            event=options.event,
            persist_index=options.persist_index,
            use_index=options.use_index,
            rebuild_index=options.rebuild_index,
            build_constants=options.build_constants,
            active_ids=active_collector_ids(options.surface, event=options.event),
            project_root=get_config().project_root,
        ),
    )
