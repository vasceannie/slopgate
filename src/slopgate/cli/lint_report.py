"""Lint CLI reporting helpers (tally, headers, summaries)."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from slopgate.constants import MAX_LINT_VIOLATIONS_SHOWN
from slopgate.lint._baseline import BaselineSyncResult, Violation

if TYPE_CHECKING:
    from slopgate.lint._config import QualityConfig

LintGateMode = Literal["new", "all"]

BASELINE_DISABLED_MESSAGE = (
    "`slopgate lint baseline` is disabled. Repo-wide rebaselining hides technical debt. "
    "Fix violations directly, or make a deliberate, human-reviewed baselines.json change that only reduces debt."
)


def _colorize(code: str, text: str, enabled: bool) -> str:
    return f"\033[{code}m{text}\033[0m" if enabled else text


def _existing_location_lines(violation: Violation, *, color: bool) -> list[str]:
    raw_locations = violation.metadata.get("existing_locations")
    if not isinstance(raw_locations, list):
        return []
    locations = [item for item in raw_locations if isinstance(item, str)]
    if not locations:
        return []
    location_text = ", ".join(locations)
    raw_more = violation.metadata.get("existing_locations_more")
    if isinstance(raw_more, int) and raw_more > 0:
        location_text += f", ... +{raw_more} more"
    marker = _colorize("2", "↳", color)
    return [f"      {marker} existing locations: {location_text}"]


@dataclass(frozen=True, slots=True)
class _RuleCounts:
    allowed: set[str]
    new_ids: set[str]
    fixed_ids: set[str]
    new_violations: list[Violation]


@dataclass(frozen=True, slots=True)
class _LintFiles:
    cfg: "QualityConfig"
    src_files: list[Path]
    test_files: list[Path]


@dataclass(frozen=True, slots=True)
class _TallyInput:
    rule_name: str
    violations: list[Violation]
    baseline: dict[str, set[str]]
    gate: LintGateMode = "new"
    details: bool = False


@dataclass(frozen=True, slots=True)
class _LintRunTotals:
    violations: int
    new: int
    fixed: int


def _rule_counts(
    rule_name: str,
    violations: list[Violation],
    baseline: dict[str, set[str]],
) -> _RuleCounts:
    allowed = baseline.get(rule_name, set())
    current_ids = {getattr(v, "stable_id") for v in violations}
    new_ids = current_ids - allowed
    return _RuleCounts(
        allowed=allowed,
        new_ids=new_ids,
        fixed_ids=allowed - current_ids,
        new_violations=[v for v in violations if getattr(v, "stable_id") in new_ids],
    )


def _rule_status(rule_name: str, *, failed: bool, color: bool) -> str:
    code = "31" if failed else "32"
    marker = "✗" if failed else "✓"
    return _colorize(code, f"{marker} {rule_name}", color)


def _rule_count_text(
    total: int,
    counts: _RuleCounts,
    *,
    color: bool,
) -> str:
    parts = [f"{total} total"]
    if counts.new_violations:
        parts.append(_colorize("31", f"{len(counts.new_violations)} NEW", color))
    if counts.fixed_ids:
        parts.append(_colorize("32", f"{len(counts.fixed_ids)} fixed", color))
    text = ", ".join(parts)
    if counts.allowed:
        text += f" {_colorize('2', f'(known debt: {len(counts.allowed)})', color)}"
    return text


def _print_new_violations(violations: list[Violation], *, color: bool) -> None:
    for violation in violations[:MAX_LINT_VIOLATIONS_SHOWN]:
        print(f"    {_colorize('31', '+', color)} {violation}")
        for line in _existing_location_lines(violation, color=color):
            print(line)
    if len(violations) > MAX_LINT_VIOLATIONS_SHOWN:
        remaining = len(violations) - MAX_LINT_VIOLATIONS_SHOWN
        print(f"    {_colorize('2', f'... and {remaining} more', color)}")


def _print_detailed_violations(
    rule_name: str,
    violations: list[Violation],
    counts: _RuleCounts,
) -> None:
    from slopgate.lint._details import format_violation_details

    for violation in violations:
        status = (
            "NEW" if getattr(violation, "stable_id") in counts.new_ids else "KNOWN-DEBT"
        )
        print()
        for line in format_violation_details(rule_name, violation, status=status):
            print(line)


def _tally_rule(input: _TallyInput) -> tuple[int, int, int]:
    color = hasattr(sys.stderr, "isatty") and sys.stderr.isatty()
    counts = _rule_counts(input.rule_name, input.violations, input.baseline)
    failed = bool(counts.new_violations) if input.gate == "new" else bool(input.violations)
    status = _rule_status(input.rule_name, failed=failed, color=color)
    print(f"  {status}  {_rule_count_text(len(input.violations), counts, color=color)}")
    _print_new_violations(counts.new_violations, color=color)
    if input.details:
        _print_detailed_violations(input.rule_name, input.violations, counts)
    return len(input.violations), len(counts.new_violations), len(counts.fixed_ids)


def _print_lint_summary(totals: _LintRunTotals, color: bool, *, gate: LintGateMode = "new") -> int:
    print()
    if gate == "all":
        if totals.violations == 0:
            print(_colorize("32", "✓ No violations", color))
            return 0
        known_debt = totals.violations - totals.new
        print(
            _colorize(
                "31",
                f"✗ {totals.violations} violation(s) must be fixed before commit "
                f"({totals.new} NEW, {known_debt} known debt)",
                color,
            )
        )
        return 1
    if totals.new == 0:
        if totals.violations == 0:
            print(_colorize("32", "✓ No violations", color))
        else:
            print(
                _colorize(
                    "32",
                    f"✓ No new violations ({totals.violations} known-debt hits remain)",
                    color,
                )
            )
        return 0
    print(_colorize("31", f"✗ {totals.new} new violation(s) introduced", color))
    print(f"  {totals.violations} total across all rules")
    return 1


def _print_scan_roots(label: str, roots: tuple[Path, ...], file_count: int) -> None:
    if len(roots) == 1:
        print(f"  {label + ':':8} {roots[0]}  ({file_count} files)")
        return
    joined = ", ".join(str(root) for root in roots)
    print(f"  {label + ':':8} [{joined}]  ({file_count} files)")


def _print_lint_header(
    lint_version: str,
    label: str,
    files: _LintFiles,
    *,
    gate: LintGateMode = "new",
) -> None:
    from slopgate.lint._baseline import _baseline_path

    suffix = f" {label}" if label else ""
    print(f"slopgate lint {lint_version}{suffix}")
    print(f"  project:  {files.cfg.project_root}")
    print(f"  baseline: {_baseline_path()}")
    if gate == "all":
        print(
            "  note:     commit gate — fails on ANY violation (fix code or shrink baseline)"
        )
    else:
        print(
            "  note:     agent/stop gate — fails on NEW violations; syncs baseline after run"
        )
    _print_scan_roots("src", files.cfg.src_roots, len(files.src_files))
    _print_scan_roots("tests", files.cfg.test_roots, len(files.test_files))
    print()


@dataclass(frozen=True, slots=True)
class _BaselineLintSyncContext:
    collectors: list[tuple[str, list[Violation]]]
    baseline: dict[str, set[str]]
    totals: _LintRunTotals
    gate: LintGateMode
    color: bool


def _lint_prune_only(totals: _LintRunTotals, *, gate: LintGateMode) -> bool:
    if gate == "new":
        return totals.new > 0
    return totals.violations > 0


def _print_baseline_sync_result(
    result: BaselineSyncResult,
    *,
    prune_only: bool,
    color: bool,
) -> None:
    if not result.wrote and result.stale_removed == 0:
        return
    parts: list[str] = []
    if result.stale_removed:
        parts.append(f"removed {result.stale_removed} stale")
    if result.wrote and not prune_only:
        parts.append("mirrored current findings")
    elif result.wrote:
        parts.append("pruned fixed debt")
    if parts:
        detail = ", ".join(parts)
        print(_colorize("32", f"  ✓ Updated baselines.json ({detail})", color))


def _sync_baseline_after_lint(context: _BaselineLintSyncContext) -> None:
    from slopgate.lint._baseline import apply_lint_baseline_sync

    prune_only = _lint_prune_only(context.totals, gate=context.gate)
    result = apply_lint_baseline_sync(
        context.collectors,
        context.baseline,
        prune_only=prune_only,
    )
    _print_baseline_sync_result(
        result,
        prune_only=prune_only,
        color=context.color,
    )


def _print_collector_results(
    collectors: list[tuple[str, list[Violation]]],
    baseline: dict[str, set[str]],
    *,
    gate: LintGateMode = "new",
    details: bool,
) -> int:
    color = hasattr(sys.stderr, "isatty") and sys.stderr.isatty()
    totals = _LintRunTotals(0, 0, 0)
    for rule_name, violations in collectors:
        if not violations:
            continue
        rule_total, rule_new, rule_fixed = _tally_rule(
            _TallyInput(
                rule_name=rule_name,
                violations=violations,
                baseline=baseline,
                gate=gate,
                details=details,
            )
        )
        totals = _LintRunTotals(
            totals.violations + rule_total,
            totals.new + rule_new,
            totals.fixed + rule_fixed,
        )
    exit_code = _print_lint_summary(totals, color, gate=gate)
    _sync_baseline_after_lint(
        _BaselineLintSyncContext(
            collectors=collectors,
            baseline=baseline,
            totals=totals,
            gate=gate,
            color=color,
        )
    )
    return exit_code
