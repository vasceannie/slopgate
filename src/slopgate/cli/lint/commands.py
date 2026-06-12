"""Lint subcommand handlers (scan, freeze, init, update)."""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from slopgate.cli.lint.git_base_debt import scan_git_base_debt
from slopgate.cli.lint.report import (
    BASELINE_DISABLED_MESSAGE,
    LintGateMode,
    BaselineInputs,
    LintFiles,
    LintHeader,
    print_collector_results,
    print_lint_header,
)
from slopgate.constants import LINT_SCOPE_ALL
from slopgate.lint._baseline import Violation


def discover_project_root(start: Path) -> Path:
    """Find the nearest project root from *start* using repo/config markers."""
    current = start.resolve()
    if current.is_file():
        current = current.parent
    markers = ("slopgate.toml", "pyproject.toml", ".git")
    for candidate in (current, *current.parents):
        if any(((candidate / marker).exists() for marker in markers)):
            return candidate
    return current


def _configured_lint_files(root: Path, *, force_all_scope: bool) -> LintFiles:
    from slopgate.lint._config import load_config
    from slopgate.lint._config import reset_quality_scope
    from slopgate.lint._config import set_config
    from slopgate.lint._config import set_quality_scope
    from slopgate.lint._helpers import find_source_files, find_test_files

    root = discover_project_root(root)
    scope_token = set_quality_scope(LINT_SCOPE_ALL if force_all_scope else None)
    cfg = load_config(root)
    set_config(cfg)
    try:
        return LintFiles(cfg, find_source_files(), find_test_files())
    finally:
        reset_quality_scope(scope_token)


def _lint_scan(
    root: Path, *, gate: LintGateMode, header_label: str, details: bool = False
) -> int:
    from slopgate.lint import __version__
    from slopgate.lint._baseline import load_baseline
    from slopgate.lint._collectors import run_all_collectors

    files = _configured_lint_files(root, force_all_scope=True)
    baseline = load_baseline()
    collectors = run_all_collectors(files.src_files, files.test_files)
    git_base_debt = None
    if gate == "new" and files.cfg.enable_git_base_debt:
        from slopgate.lint._config import set_config

        git_base_debt = scan_git_base_debt(
            files.cfg.project_root, configured_lint_files=_configured_lint_files
        )
        set_config(files.cfg)
    print_lint_header(
        LintHeader(
            lint_version=__version__,
            label=header_label,
            files=files,
            gate=gate,
            git_base_note=git_base_debt.note if git_base_debt is not None else None,
        )
    )
    baseline_inputs = BaselineInputs(
        stored=baseline,
        accepted=git_base_debt.rules if git_base_debt is not None else {},
    )
    return print_collector_results(
        collectors, baseline_inputs, gate=gate, details=details
    )


@dataclass(frozen=True, slots=True)
class _LintScanCommand:
    gate: LintGateMode
    header_label: str

    def __call__(self, root: Path, *, details: bool = False) -> int:
        project_root = discover_project_root(root)
        scan_details = details
        return _lint_scan(
            project_root,
            gate=self.gate,
            header_label=self.header_label,
            details=scan_details,
        )


lint_check = _LintScanCommand(gate="new", header_label="")
lint_strict = _LintScanCommand(
    gate=cast(LintGateMode, LINT_SCOPE_ALL), header_label="strict"
)


def lint_baseline(_root: Path) -> int:
    print(BASELINE_DISABLED_MESSAGE)
    return 1


def lint_freeze(root: Path) -> int:
    """Snapshot current lint findings into baselines.json when rules are still empty."""
    from slopgate.lint import __version__
    from slopgate.lint._baseline import baseline_path, load_baseline, save_baseline
    from slopgate.lint._collectors import run_all_collectors

    project_root = discover_project_root(root)
    files = _configured_lint_files(project_root, force_all_scope=True)
    existing = load_baseline()
    if any(existing.values()):
        print("Baseline already records violations; refusing to overwrite.")
        print(
            "  Fix violations or edit baselines.json to reduce debt. Repo-wide rebaselining stays disabled (`slopgate lint baseline`)."
        )
        return 1
    print_lint_header(LintHeader(__version__, "freeze", files, gate="new"))
    violations_by_rule: dict[str, list[Violation]] = {}
    total = 0
    for rule_name, violations in run_all_collectors(files.src_files, files.test_files):
        if not violations:
            continue
        violations_by_rule[rule_name] = violations
        total += len(violations)
    save_baseline(violations_by_rule)
    destination = baseline_path()
    print(
        f"✓ Froze {total} violation(s) across {len(violations_by_rule)} rule(s) into {destination}"
    )
    print(
        "  Future `slopgate lint` fails only on NEW violations; fix listed debt and shrink this file."
    )
    return 0


def lint_test_integrity(root: Path, *, details: bool = False) -> int:
    from slopgate.lint import __version__
    from slopgate.lint._baseline import load_baseline
    from slopgate.lint._collectors import run_test_integrity_collectors

    files = _configured_lint_files(root, force_all_scope=False)
    print_lint_header(LintHeader(__version__, "test-integrity", files, gate="new"))
    collectors = run_test_integrity_collectors(files.src_files, files.test_files)
    return print_collector_results(
        collectors, load_baseline(), gate="new", details=details
    )


def lint_init(root: Path) -> int:
    from slopgate.lint import __version__
    from slopgate.lint._updater import render_slopgate_toml

    root.mkdir(parents=True, exist_ok=True)
    destination = root / "slopgate.toml"
    if destination.exists():
        print(f"Already exists: {destination}")
        print("  To add missing keys, run: slopgate lint update")
        return 1
    _ = destination.write_text(
        render_slopgate_toml(version=__version__), encoding="utf-8"
    )
    print(f"✓ Created {destination}")
    print("  Edit it to match your project, then run: slopgate lint check")
    return 0


def lint_update(root: Path, *, dry_run: bool = False) -> int:
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
    total_keys = sum((len(keys) for keys in missing.values()))
    print(
        f"{('Would add' if dry_run else 'Added')} {total_keys} key(s) across {len(missing)} section(s):"
    )
    for section, keys in missing.items():
        for key in keys:
            print(f"  [{section}] {key}")
    if dry_run:
        print("  (dry run)")
    else:
        print(f"✓ Updated {destination}")
    return 0
