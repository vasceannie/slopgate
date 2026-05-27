from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from vibeforcer.constants import MAX_LINT_VIOLATIONS_SHOWN
from vibeforcer.lint._baseline import Violation

if TYPE_CHECKING:
    from vibeforcer.lint._config import QualityConfig

BASELINE_DISABLED_MESSAGE = (
    "`vibeforcer lint baseline` is disabled. Repo-wide rebaselining hides technical debt. "
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


def _rule_status(rule_name: str, *, has_new: bool, color: bool) -> str:
    code = "31" if has_new else "32"
    marker = "✗" if has_new else "✓"
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
        text += f" {_colorize('2', f'(baseline: {len(counts.allowed)})', color)}"
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
    from vibeforcer.lint._details import format_violation_details

    for violation in violations:
        status = "NEW" if getattr(violation, "stable_id") in counts.new_ids else "BASELINED"
        print()
        for line in format_violation_details(rule_name, violation, status=status):
            print(line)


def _tally_rule(
    rule_name: str,
    violations: list[Violation],
    baseline: dict[str, set[str]],
    *,
    details: bool = False,
) -> tuple[int, int, int]:
    color = hasattr(sys.stderr, "isatty") and sys.stderr.isatty()
    counts = _rule_counts(rule_name, violations, baseline)
    status = _rule_status(rule_name, has_new=bool(counts.new_violations), color=color)
    print(f"  {status}  {_rule_count_text(len(violations), counts, color=color)}")
    _print_new_violations(counts.new_violations, color=color)
    if details:
        _print_detailed_violations(rule_name, violations, counts)
    return len(violations), len(counts.new_violations), len(counts.fixed_ids)


def _print_lint_summary(
    total_v: int,
    total_n: int,
    total_f: int,
    color: bool,
) -> int:
    print()
    if total_n == 0:
        print(
            _colorize(
                "32", f"✓ No new violations ({total_v} total, all baselined)", color
            )
        )
        if total_f:
            print(
                _colorize(
                    "33",
                    f"  ℹ {total_f} fixed — update baselines.json only as a deliberate debt reduction, not via repo-wide rebaselining",
                    color,
                )
            )
        return 0
    print(_colorize("31", f"✗ {total_n} new violation(s) introduced", color))
    print(f"  {total_v} total across all rules")
    return 1


def _discover_project_root(start: Path) -> Path:
    """Find the nearest project root from *start* using repo/config markers."""

    current = start.resolve()
    if current.is_file():
        current = current.parent
    markers = ("quality_gate.toml", "pyproject.toml", ".git")
    for candidate in (current, *current.parents):
        if any((candidate / marker).exists() for marker in markers):
            return candidate
    return current


@dataclass(frozen=True, slots=True)
class _LintFiles:
    cfg: "QualityConfig"
    src_files: list[Path]
    test_files: list[Path]


def _restore_quality_scope(old_quality_scope: str | None) -> None:
    if old_quality_scope is None:
        os.environ.pop("QUALITY_SCOPE", None)
    else:
        os.environ["QUALITY_SCOPE"] = old_quality_scope


def _configured_lint_files(
    root: Path,
    *,
    force_all_scope: bool,
) -> _LintFiles:
    from vibeforcer.lint._config import load_config as load_qg_config
    from vibeforcer.lint._config import set_config as set_qg_config
    from vibeforcer.lint._helpers import find_source_files, find_test_files

    root = _discover_project_root(root)
    old_quality_scope = os.environ.get("QUALITY_SCOPE")
    if force_all_scope:
        os.environ["QUALITY_SCOPE"] = "all"
    cfg = load_qg_config(root)
    set_qg_config(cfg)
    try:
        return _LintFiles(cfg, find_source_files(), find_test_files())
    finally:
        if force_all_scope:
            _restore_quality_scope(old_quality_scope)


def _print_lint_header(
    lint_version: str,
    label: str,
    files: _LintFiles,
) -> None:
    suffix = f" {label}" if label else ""
    print(f"vibeforcer lint {lint_version}{suffix}")
    print(f"  project: {files.cfg.project_root}")
    print(f"  src:     {files.cfg.src_root}  ({len(files.src_files)} files)")
    print(f"  tests:   {files.cfg.tests_root}  ({len(files.test_files)} files)")
    print()


def _print_collector_results(
    collectors: list[tuple[str, list[Violation]]],
    baseline: dict[str, set[str]],
    *,
    details: bool,
) -> int:
    color = hasattr(sys.stderr, "isatty") and sys.stderr.isatty()
    totals = [0, 0, 0]
    for rule_name, violations in collectors:
        if not violations:
            continue
        counts = _tally_rule(rule_name, violations, baseline, details=details)
        for index, count in enumerate(counts):
            totals[index] += count
    return _print_lint_summary(totals[0], totals[1], totals[2], color)


def _lint_check(root: Path, *, details: bool = False) -> int:
    from vibeforcer.lint import __version__ as lint_version
    from vibeforcer.lint._baseline import load_baseline
    from vibeforcer.lint._collectors import run_all_collectors

    files = _configured_lint_files(root, force_all_scope=True)
    _print_lint_header(lint_version, "", files)
    collectors = run_all_collectors(files.src_files, files.test_files)
    return _print_collector_results(collectors, load_baseline(), details=details)


def _lint_baseline(_root: Path) -> int:
    print(BASELINE_DISABLED_MESSAGE)
    return 1


def _lint_test_integrity(root: Path, *, details: bool = False) -> int:
    from vibeforcer.lint import __version__ as lint_version
    from vibeforcer.lint._baseline import load_baseline
    from vibeforcer.lint._collectors import run_test_integrity_collectors

    files = _configured_lint_files(root, force_all_scope=False)
    _print_lint_header(lint_version, "test-integrity", files)
    collectors = run_test_integrity_collectors(files.src_files, files.test_files)
    return _print_collector_results(collectors, load_baseline(), details=details)


def _lint_init(root: Path) -> int:
    from vibeforcer.lint import __version__ as lint_version
    from vibeforcer.lint._updater import render_quality_gate_toml

    root.mkdir(parents=True, exist_ok=True)
    destination = root / "quality_gate.toml"
    if destination.exists():
        print(f"Already exists: {destination}")
        print("  To add missing keys, run: vibeforcer lint update")
        return 1

    _ = destination.write_text(
        render_quality_gate_toml(version=lint_version), encoding="utf-8"
    )
    print(f"✓ Created {destination}")
    print("  Edit it to match your project, then run: vibeforcer lint check")
    return 0


def _lint_update(root: Path, *, dry_run: bool = False) -> int:
    from vibeforcer.lint._updater import update_toml_file

    destination = root / "quality_gate.toml"
    if not destination.exists():
        print(f"No quality_gate.toml found at {root}")
        print("  Run `vibeforcer lint init` first.")
        return 1

    missing = update_toml_file(destination, dry_run=dry_run)
    if not missing:
        print("✓ Config is up to date")
        return 0

    total_keys = sum(len(keys) for keys in missing.values())
    print(
        f"{'Would add' if dry_run else 'Added'} {total_keys} key(s) across {len(missing)} section(s):"
    )
    for section, keys in missing.items():
        for key in keys:
            print(f"  [{section}] {key}")
    if dry_run:
        print("  (dry run)")
    else:
        print(f"✓ Updated {destination}")
    return 0


def cmd_lint(args: argparse.Namespace) -> int:
    raw_lint_command = getattr(args, "lint_command", None)
    lint_command = raw_lint_command if isinstance(raw_lint_command, str) else "check"
    raw_path = getattr(args, "path", ".")
    path_value = raw_path if isinstance(raw_path, str) and raw_path else "."
    root = Path(path_value).resolve()
    dispatch = {
        "baseline": _lint_baseline,
        "init": _lint_init,
    }
    if lint_command == "check":
        raw_details = getattr(args, "details", False)
        return _lint_check(
            Path.cwd(),
            details=raw_details if isinstance(raw_details, bool) else False,
        )
    if lint_command == "test-integrity":
        raw_details = getattr(args, "details", False)
        return _lint_test_integrity(
            Path.cwd(),
            details=raw_details if isinstance(raw_details, bool) else False,
        )
    handler = dispatch.get(lint_command)
    if handler is not None:
        return handler(root)
    if lint_command == "update":
        raw_dry_run = getattr(args, "dry_run", False)
        return _lint_update(
            _discover_project_root(root),
            dry_run=raw_dry_run if isinstance(raw_dry_run, bool) else False,
        )
    return 1
