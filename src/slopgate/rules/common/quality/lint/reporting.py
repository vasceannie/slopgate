"""Touched-file lint reporting shared by projected and authoritative rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from slopgate.constants import (
    METADATA_PATH,
    PYTEST_TEST_PREFIX,
    QUALITY_FAILURE_PREVIEW_LIMIT,
)
from slopgate.lint._config import get_config, load_config, set_config
from slopgate.util.path_filters import is_third_party_or_virtualenv_path
from slopgate.util.payloads import lower_path

from ..guidance import (
    has_oversized_module_failure,
    lint_check_instruction,
    lint_target_summary,
    post_lint_oversized_guidance,
    preview_with_overflow,
)

if TYPE_CHECKING:
    from slopgate.context import HookContext
    from slopgate.lint._baseline import Violation

LINT_DETAIL_LIMIT = 3


@dataclass(frozen=True, slots=True)
class TouchedLintReport:
    failures: list[str]
    details: list[list[str]]
    targets: list[str]
    first_diagnostic: dict[str, object] | None = None
    collector_ids: dict[str, list[str]] = field(default_factory=dict)


def _candidate_file(ctx: HookContext, candidate: str) -> Path | None:
    if not candidate.lower().endswith(".py"):
        return None
    if is_third_party_or_virtualenv_path(candidate):
        return None
    path = Path(candidate)
    full = path if path.is_absolute() else ctx.config.repo_root / path
    if not full.exists() or not full.is_file():
        return None
    return full.resolve()


def resolve_python_candidates(ctx: HookContext) -> tuple[list[Path], list[Path]]:
    src_files: list[Path] = []
    test_files: list[Path] = []
    for candidate in ctx.candidate_paths:
        full = _candidate_file(ctx, candidate)
        if full is None:
            continue
        normalized = lower_path(str(full))
        if "/tests/" in normalized or full.name.startswith(PYTEST_TEST_PREFIX):
            test_files.append(full)
        else:
            src_files.append(full)
    return src_files, test_files


def _touched_lint_relative_paths(
    src_files: list[Path], test_files: list[Path]
) -> set[str]:
    from slopgate.lint._helpers import relative_path

    touched = {relative_path(path) for path in [*src_files, *test_files]}
    if src_files:
        touched.add("<project>")
    return touched


def violation_details(rule_name: str, violations: list[Violation]) -> list[list[str]]:
    from slopgate.lint._details import format_violation_details

    groups = [
        format_violation_details(rule_name, violation, status="HOOK")
        for violation in violations[:LINT_DETAIL_LIMIT]
    ]
    remaining = len(violations) - LINT_DETAIL_LIMIT
    if remaining > 0 and groups:
        groups[-1].append(f"    +{remaining} more {rule_name} violation(s) not shown.")
    return groups


def _first_lint_diagnostic(rule_name: str, violation: Violation) -> dict[str, object]:
    from slopgate.lint._details import line_number, location

    diagnostic: dict[str, object] = {
        "collector": rule_name,
        "location": location(violation),
        METADATA_PATH: violation.relative_path,
    }
    line = line_number(violation)
    if line is not None:
        diagnostic["line"] = line
    return diagnostic


def _first_lint_diagnostic_text(diagnostic: dict[str, object] | None) -> str:
    if diagnostic is None:
        return ""
    location_value = diagnostic.get("location")
    collector = diagnostic.get("collector")
    if not isinstance(location_value, str) or not isinstance(collector, str):
        return ""
    return f"First lint target: {location_value} ({collector}). "


def collect_lint_report_for_files(
    src_files: list[Path],
    test_files: list[Path],
    *,
    config_root: Path,
    deterministic_file_only: bool = False,
) -> TouchedLintReport:
    if not src_files and not test_files:
        return TouchedLintReport([], [], [])
    from slopgate.lint._collectors import run_touched_collectors

    previous_config = get_config()
    try:
        set_config(load_config(config_root))
        touched_paths = _touched_lint_relative_paths(src_files, test_files)
        lint_targets = sorted(path for path in touched_paths if path != "<project>")
        failures: list[str] = []
        details: list[list[str]] = []
        collector_ids: dict[str, list[str]] = {}
        first_diagnostic: dict[str, object] | None = None
        results = (
            run_touched_collectors(
                src_files,
                test_files,
                deterministic_file_only=True,
            )
            if deterministic_file_only
            else run_touched_collectors(src_files, test_files)
        )
        for rule_name, violations in results:
            scoped = [
                item for item in violations if item.relative_path in touched_paths
            ]
            if not scoped:
                continue
            if first_diagnostic is None:
                first_diagnostic = _first_lint_diagnostic(rule_name, scoped[0])
            failures.append(f"{rule_name}: {len(scoped)}")
            details.extend(violation_details(rule_name, scoped))
            collector_ids[rule_name] = sorted(item.stable_id for item in scoped)
        return TouchedLintReport(
            failures, details, lint_targets, first_diagnostic, collector_ids
        )
    finally:
        set_config(previous_config)


def collect_touched_lint_report(ctx: HookContext) -> TouchedLintReport:
    src_files, test_files = resolve_python_candidates(ctx)
    return collect_lint_report_for_files(
        src_files, test_files, config_root=ctx.config.repo_root
    )


def collect_touched_lint_failures(
    ctx: HookContext,
) -> tuple[list[str], list[list[str]], list[str]]:
    report = collect_touched_lint_report(ctx)
    return report.failures, report.details, report.targets


def python_lint_targets(ctx: HookContext) -> list[str]:
    return [
        path
        for path in ctx.candidate_paths
        if path.lower().endswith(".py") and not is_third_party_or_virtualenv_path(path)
    ]


def _lint_detail_text(details: list[list[str]]) -> str:
    if not details:
        return ""
    groups = ["\n".join(group[:12]) for group in details]
    return " Blocking lint collector details:\n" + "\n\n".join(groups)


def lint_message(
    failures: list[str],
    details: list[list[str]],
    targets: list[str],
    first_diagnostic: dict[str, object] | None,
) -> str:
    target_summary = lint_target_summary(targets)
    instruction = lint_check_instruction(targets)
    message = (
        f"Touched-file lint detectors found issues{target_summary}. "
        f"{_first_lint_diagnostic_text(first_diagnostic)}"
        f"{preview_with_overflow(failures, limit=QUALITY_FAILURE_PREVIEW_LIMIT)}. "
        f"{instruction} Repair touched files before continuing."
    )
    message += _lint_detail_text(details)
    if has_oversized_module_failure(failures):
        message = f"{message} {post_lint_oversized_guidance(targets)}"
    return message


__all__ = [
    "TouchedLintReport",
    "collect_lint_report_for_files",
    "collect_touched_lint_report",
    "collect_touched_lint_failures",
    "lint_message",
    "python_lint_targets",
    "resolve_python_candidates",
    "violation_details",
]
