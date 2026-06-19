"""Lint CLI reporting helpers (tally, headers, summaries)."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from slopgate.constants import MAX_LINT_VIOLATIONS_SHOWN
from slopgate.cli.lint.report_format import colorize, existing_location_lines
from slopgate.lint._baseline import BaselineSyncResult, Violation

if TYPE_CHECKING:
    from slopgate.lint._config import QualityConfig

LintGateMode = Literal["new", "all"]

BASELINE_DISABLED_MESSAGE = (
    "`slopgate lint baseline` is disabled. Repo-wide rebaselining hides technical debt. "
    "Fix violations directly, or make a deliberate, human-reviewed baselines.json change that only reduces debt."
)


@dataclass(frozen=True, slots=True)
class _RuleCounts:
    allowed: set[str]
    new_ids: set[str]
    fixed_ids: set[str]
    new_violations: list[Violation]


@dataclass(frozen=True, slots=True)
class LintFiles:
    cfg: "QualityConfig"
    src_files: list[Path]
    test_files: list[Path]


@dataclass(frozen=True, slots=True)
class LintHeader:
    lint_version: str
    label: str
    files: LintFiles
    gate: LintGateMode = "new"
    git_base_note: str | None = None


@dataclass(frozen=True, slots=True)
class TallyInput:
    rule_name: str
    violations: list[Violation]
    baseline: dict[str, set[str]]
    gate: LintGateMode = "new"
    details: bool = False


@dataclass(frozen=True, slots=True)
class LintRunTotals:
    violations: int
    new: int
    fixed: int


@dataclass(frozen=True, slots=True)
class BaselineInputs:
    stored: dict[str, set[str]]
    accepted: dict[str, set[str]]

    @property
    def effective(self) -> dict[str, set[str]]:
        return _merge_rule_ids(self.stored, self.accepted)


def _coerce_baseline_inputs(
    baseline: dict[str, set[str]] | BaselineInputs,
) -> BaselineInputs:
    if isinstance(baseline, BaselineInputs):
        return baseline
    return BaselineInputs(stored=baseline, accepted={})


def _merge_rule_ids(
    left: dict[str, set[str]],
    right: dict[str, set[str]],
) -> dict[str, set[str]]:
    merged: dict[str, set[str]] = {rule: set(ids) for rule, ids in left.items()}
    for rule, ids in right.items():
        merged.setdefault(rule, set()).update(ids)
    return merged


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
    return colorize(code, f"{marker} {rule_name}", color)


def _rule_count_text(
    total: int,
    counts: _RuleCounts,
    *,
    color: bool,
) -> str:
    parts = [f"{total} total"]
    if counts.new_violations:
        parts.append(colorize("31", f"{len(counts.new_violations)} NEW", color))
    if counts.fixed_ids:
        parts.append(colorize("32", f"{len(counts.fixed_ids)} fixed", color))
    text = ", ".join(parts)
    if counts.allowed:
        text += f" {colorize('2', f'(known debt: {len(counts.allowed)})', color)}"
    return text


def _print_new_violations(violations: list[Violation], *, color: bool) -> None:
    for violation in violations[:MAX_LINT_VIOLATIONS_SHOWN]:
        print(f"    {colorize('31', '+', color)} {violation}")
        for line in existing_location_lines(violation, color=color):
            print(line)
    if len(violations) > MAX_LINT_VIOLATIONS_SHOWN:
        remaining = len(violations) - MAX_LINT_VIOLATIONS_SHOWN
        print(f"    {colorize('2', f'... and {remaining} more', color)}")


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


def tally_rule(input: TallyInput) -> tuple[int, int, int]:
    color = hasattr(sys.stderr, "isatty") and sys.stderr.isatty()
    counts = _rule_counts(input.rule_name, input.violations, input.baseline)
    failed = (
        bool(counts.new_violations) if input.gate == "new" else bool(input.violations)
    )
    status = _rule_status(input.rule_name, failed=failed, color=color)
    print(f"  {status}  {_rule_count_text(len(input.violations), counts, color=color)}")
    _print_new_violations(counts.new_violations, color=color)
    if input.details:
        _print_detailed_violations(input.rule_name, input.violations, counts)
    return len(input.violations), len(counts.new_violations), len(counts.fixed_ids)


def print_lint_summary(
    totals: LintRunTotals, color: bool, *, gate: LintGateMode = "new"
) -> int:
    print()
    if gate == "all":
        if totals.violations == 0:
            print(colorize("32", "✓ No violations", color))
            return 0
        known_debt = totals.violations - totals.new
        print(
            colorize(
                "31",
                f"✗ {totals.violations} violation(s) must be fixed before commit "
                f"({totals.new} NEW, {known_debt} known debt)",
                color,
            )
        )
        return 1
    if totals.new == 0:
        if totals.violations == 0:
            print(colorize("32", "✓ No violations", color))
        else:
            print(
                colorize(
                    "32",
                    f"✓ No new violations ({totals.violations} known-debt hits remain)",
                    color,
                )
            )
        return 0
    print(colorize("31", f"✗ {totals.new} new violation(s) introduced", color))
    print(f"  {totals.violations} total across all rules")
    return 1


def _print_scan_roots(label: str, roots: tuple[Path, ...], file_count: int) -> None:
    if len(roots) == 1:
        print(f"  {label + ':':8} {roots[0]}  ({file_count} files)")
        return
    joined = ", ".join(str(root) for root in roots)
    print(f"  {label + ':':8} [{joined}]  ({file_count} files)")


def print_lint_header(header: LintHeader) -> None:
    from slopgate.lint._baseline import baseline_path
    from slopgate.cli._version_check import check_version, format_update_notice

    suffix = f" {header.label}" if header.label else ""
    print(f"slopgate lint {header.lint_version}{suffix}")

    version_info = check_version(header.lint_version)
    notice = format_update_notice(version_info.current, version_info.latest)
    if notice:
        print(f"  {notice}")

    print(f"  project:  {header.files.cfg.project_root}")
    print(f"  baseline: {baseline_path()}")
    if header.git_base_note:
        print(f"  git base: {header.git_base_note}")
    if header.gate == "all":
        print(
            "  note:     commit gate — fails on ANY violation (fix code or shrink baseline)"
        )
    else:
        print(
            "  note:     agent/stop gate — fails on branch/WIP violations; prunes fixed debt after run"
        )
    _print_scan_roots("src", header.files.cfg.src_roots, len(header.files.src_files))
    _print_scan_roots(
        "tests", header.files.cfg.test_roots, len(header.files.test_files)
    )
    print()


@dataclass(frozen=True, slots=True)
class _BaselineLintSyncContext:
    collectors: list[tuple[str, list[Violation]]]
    baseline: dict[str, set[str]]
    accepted_baseline: dict[str, set[str]]
    totals: LintRunTotals
    gate: LintGateMode
    color: bool


def _lint_prune_only(totals: LintRunTotals, *, gate: LintGateMode) -> bool:
    return True


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
    if result.inherited_added:
        parts.append(f"recorded {result.inherited_added} git-base inherited")
    if result.wrote and not result.inherited_added:
        parts.append("pruned fixed debt")
    if parts:
        detail = ", ".join(parts)
        print(colorize("32", f"  ✓ Updated baselines.json ({detail})", color))


def _sync_baseline_after_lint(context: _BaselineLintSyncContext) -> None:
    from slopgate.lint._baseline import apply_lint_baseline_sync

    prune_only = _lint_prune_only(context.totals, gate=context.gate)
    result = apply_lint_baseline_sync(
        context.collectors,
        context.baseline,
        prune_only=prune_only,
        accepted_baseline=context.accepted_baseline,
    )
    _print_baseline_sync_result(
        result,
        prune_only=prune_only,
        color=context.color,
    )


def print_collector_results(
    collectors: list[tuple[str, list[Violation]]],
    baseline: dict[str, set[str]] | BaselineInputs,
    *,
    gate: LintGateMode = "new",
    details: bool,
) -> int:
    color = hasattr(sys.stderr, "isatty") and sys.stderr.isatty()
    baseline_inputs = _coerce_baseline_inputs(baseline)
    totals = LintRunTotals(0, 0, 0)
    for rule_name, violations in collectors:
        if not violations:
            continue
        rule_total, rule_new, rule_fixed = tally_rule(
            TallyInput(
                rule_name=rule_name,
                violations=violations,
                baseline=baseline_inputs.effective,
                gate=gate,
                details=details,
            )
        )
        totals = LintRunTotals(
            totals.violations + rule_total,
            totals.new + rule_new,
            totals.fixed + rule_fixed,
        )
    exit_code = print_lint_summary(totals, color, gate=gate)
    _sync_baseline_after_lint(
        _BaselineLintSyncContext(
            collectors=collectors,
            baseline=baseline_inputs.stored,
            accepted_baseline=baseline_inputs.accepted,
            totals=totals,
            gate=gate,
            color=color,
        )
    )
    return exit_code
