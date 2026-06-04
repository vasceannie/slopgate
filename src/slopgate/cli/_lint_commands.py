"""Lint subcommand handlers (scan, freeze, init, update)."""

from __future__ import annotations

import os
from pathlib import Path

from slopgate.cli.lint_report import (
    BASELINE_DISABLED_MESSAGE,
    LintGateMode,
    _LintFiles,
    _print_collector_results,
    _print_lint_header,
)
from slopgate.lint._baseline import Violation


def _discover_project_root(start: Path) -> Path:
    """Find the nearest project root from *start* using repo/config markers."""

    current = start.resolve()
    if current.is_file():
        current = current.parent
    markers = ("slopgate.toml", "pyproject.toml", ".git")
    for candidate in (current, *current.parents):
        if any((candidate / marker).exists() for marker in markers):
            return candidate
    return current


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
    from slopgate.lint._config import load_config as load_qg_config
    from slopgate.lint._config import set_config as set_qg_config
    from slopgate.lint._helpers import find_source_files, find_test_files

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


def _lint_scan(
    root: Path,
    *,
    gate: LintGateMode,
    header_label: str,
    details: bool = False,
) -> int:
    from slopgate.lint import __version__ as lint_version
    from slopgate.lint._baseline import load_baseline
    from slopgate.lint._collectors import run_all_collectors

    files = _configured_lint_files(root, force_all_scope=True)
    _print_lint_header(lint_version, header_label, files, gate=gate)
    collectors = run_all_collectors(files.src_files, files.test_files)
    return _print_collector_results(
        collectors, load_baseline(), gate=gate, details=details
    )


def _lint_check(root: Path, *, details: bool = False) -> int:
    return _lint_scan(root, gate="new", header_label="", details=details)


def _lint_strict(root: Path, *, details: bool = False) -> int:
    return _lint_scan(root, gate="all", header_label="strict", details=details)


def _lint_baseline(_root: Path) -> int:
    print(BASELINE_DISABLED_MESSAGE)
    return 1


def _baseline_has_recorded_debt(baseline: dict[str, set[str]]) -> bool:
    return any(allowed_ids for allowed_ids in baseline.values())


def _lint_freeze(root: Path) -> int:
    """Snapshot current lint findings into baselines.json when rules are still empty."""
    from slopgate.lint import __version__ as lint_version
    from slopgate.lint._baseline import _baseline_path, load_baseline, save_baseline
    from slopgate.lint._collectors import run_all_collectors

    project_root = _discover_project_root(root)
    files = _configured_lint_files(project_root, force_all_scope=True)
    existing = load_baseline()
    if _baseline_has_recorded_debt(existing):
        print("Baseline already records violations; refusing to overwrite.")
        print(
            "  Fix violations or edit baselines.json to reduce debt. "
            "Repo-wide rebaselining stays disabled (`slopgate lint baseline`)."
        )
        return 1
    _print_lint_header(lint_version, "freeze", files, gate="new")

    violations_by_rule: dict[str, list[Violation]] = {}
    total = 0
    for rule_name, violations in run_all_collectors(files.src_files, files.test_files):
        if not violations:
            continue
        violations_by_rule[rule_name] = violations
        total += len(violations)

    save_baseline(violations_by_rule)
    destination = _baseline_path()
    print(
        f"✓ Froze {total} violation(s) across {len(violations_by_rule)} rule(s) "
        f"into {destination}"
    )
    print(
        "  Future `slopgate lint` fails only on NEW violations; fix listed debt and shrink this file."
    )
    return 0


def _lint_test_integrity(root: Path, *, details: bool = False) -> int:
    from slopgate.lint import __version__ as lint_version
    from slopgate.lint._baseline import load_baseline
    from slopgate.lint._collectors import run_test_integrity_collectors

    files = _configured_lint_files(root, force_all_scope=False)
    _print_lint_header(lint_version, "test-integrity", files, gate="new")
    collectors = run_test_integrity_collectors(files.src_files, files.test_files)
    return _print_collector_results(
        collectors, load_baseline(), gate="new", details=details
    )


def _lint_init(root: Path) -> int:
    from slopgate.lint import __version__ as lint_version
    from slopgate.lint._updater import render_slopgate_toml

    root.mkdir(parents=True, exist_ok=True)
    destination = root / "slopgate.toml"
    if destination.exists():
        print(f"Already exists: {destination}")
        print("  To add missing keys, run: slopgate lint update")
        return 1

    _ = destination.write_text(
        render_slopgate_toml(version=lint_version), encoding="utf-8"
    )
    print(f"✓ Created {destination}")
    print("  Edit it to match your project, then run: slopgate lint check")
    return 0


def _lint_update(root: Path, *, dry_run: bool = False) -> int:
    from slopgate.lint._updater import update_toml_file

    destination = root / "slopgate.toml"
    if not destination.exists():
        print(f"No slopgate.toml found at {root}")
        print("  Run `slopgate lint init` first.")
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
