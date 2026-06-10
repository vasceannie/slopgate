"""Lint subcommand handlers (scan, freeze, init, update)."""

from __future__ import annotations
import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from slopgate.cli.lint_report import (
    BASELINE_DISABLED_MESSAGE,
    LintGateMode,
    BaselineInputs,
    LintFiles,
    LintHeader,
    print_collector_results,
    print_lint_header,
)
from slopgate.lint._baseline import Violation


@dataclass(frozen=True, slots=True)
class _GitBaseDebt:
    ref_name: str
    base_sha: str
    rules: dict[str, set[str]]

    @property
    def inherited_count(self) -> int:
        return sum((len(ids) for ids in self.rules.values()))

    @property
    def note(self) -> str:
        return f"{self.ref_name} @ {self.base_sha[:12]} ({self.inherited_count} inherited id(s))"


def _run_git(root: Path, *args: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), *args],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return _stripped_output(completed.stdout)


def _stripped_output(output: str) -> str | None:
    stripped = output.strip()
    if not stripped:
        return None
    return stripped


def _candidate_base_refs(root: Path) -> list[str]:
    candidates: list[str] = []
    explicit = os.environ.get("SLOPGATE_LINT_BASE_REF")
    if explicit:
        candidates.append(explicit)
    upstream = _run_git(
        root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"
    )
    if upstream:
        candidates.append(upstream)
    candidates.extend(["origin/main", "origin/master", "main", "master"])
    unique: list[str] = []
    for candidate in candidates:
        if candidate not in unique:
            unique.append(candidate)
    return unique


def _is_current_branch_ref(ref: str, current_branch: str | None) -> bool:
    if current_branch is None or current_branch == "HEAD":
        return False
    return ref in {current_branch, f"refs/heads/{current_branch}"}


def _discover_git_base(root: Path) -> tuple[str, str] | None:
    head = _run_git(root, "rev-parse", "--verify", "HEAD^{commit}")
    if head is None:
        return None
    current_branch = _run_git(root, "rev-parse", "--abbrev-ref", "HEAD")
    for ref in _candidate_base_refs(root):
        if _run_git(root, "rev-parse", "--verify", f"{ref}^{{commit}}") is None:
            continue
        base_sha = _run_git(root, "merge-base", "HEAD", ref)
        if base_sha and (
            base_sha != head or not _is_current_branch_ref(ref, current_branch)
        ):
            return (ref, base_sha)
    return None


def _extract_git_archive(root: Path, base_sha: str, destination: Path) -> bool:
    git_process = subprocess.Popen(
        ["git", "-C", str(root), "archive", "--format=tar", base_sha],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    if git_process.stdout is None:
        _ = git_process.wait(timeout=10)
        return False
    try:
        extract = subprocess.run(
            ["tar", "-xf", "-", "-C", str(destination)],
            check=False,
            stdin=git_process.stdout,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        git_process.kill()
        return False
    finally:
        git_process.stdout.close()
    return git_process.wait(timeout=10) == 0 and extract.returncode == 0


def _collector_ids_by_rule(
    collectors: list[tuple[str, list[Violation]]],
) -> dict[str, set[str]]:
    return {
        rule: {violation.stable_id for violation in violations}
        for rule, violations in collectors
        if violations
    }


def _scan_git_base_debt(project_root: Path) -> _GitBaseDebt | None:
    from slopgate.lint._collectors import run_all_collectors

    discovered = _discover_git_base(project_root)
    if discovered is None:
        return None
    ref_name, base_sha = discovered
    with tempfile.TemporaryDirectory(prefix="slopgate-git-base-") as tmpdir:
        archive_root = Path(tmpdir)
        if not _extract_git_archive(project_root, base_sha, archive_root):
            return None
        files = _configured_lint_files(archive_root, force_all_scope=True)
        collectors = run_all_collectors(files.src_files, files.test_files)
    rules = _collector_ids_by_rule(collectors)
    if not rules:
        return None
    return _GitBaseDebt(ref_name=ref_name, base_sha=base_sha, rules=rules)


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


def _restore_quality_scope(old_quality_scope: str | None) -> None:
    if old_quality_scope is None:
        os.environ.pop("QUALITY_SCOPE", None)
    else:
        os.environ["QUALITY_SCOPE"] = old_quality_scope


def _configured_lint_files(root: Path, *, force_all_scope: bool) -> LintFiles:
    from slopgate.lint._config import load_config
    from slopgate.lint._config import set_config
    from slopgate.lint._helpers import find_source_files, find_test_files

    root = discover_project_root(root)
    old_quality_scope = os.environ.get("QUALITY_SCOPE")
    if force_all_scope:
        os.environ["QUALITY_SCOPE"] = "all"
    cfg = load_config(root)
    set_config(cfg)
    try:
        return LintFiles(cfg, find_source_files(), find_test_files())
    finally:
        if force_all_scope:
            _restore_quality_scope(old_quality_scope)


def _lint_scan(
    root: Path, *, gate: LintGateMode, header_label: str, details: bool = False
) -> int:
    from slopgate.lint import __version__
    from slopgate.lint._baseline import load_baseline
    from slopgate.lint._collectors import run_all_collectors

    files = _configured_lint_files(root, force_all_scope=True)
    baseline = load_baseline()
    collectors = run_all_collectors(files.src_files, files.test_files)
    git_base_debt = (
        _scan_git_base_debt(files.cfg.project_root)
        if gate == "new" and files.cfg.enable_git_base_debt
        else None
    )
    files = _configured_lint_files(files.cfg.project_root, force_all_scope=True)
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


def lint_check(root: Path, *, details: bool = False) -> int:
    return _lint_scan(root, gate="new", header_label="", details=details)


def lint_strict(root: Path, *, details: bool = False) -> int:
    return _lint_scan(root, gate="all", header_label="strict", details=details)


def lint_baseline(_root: Path) -> int:
    print(BASELINE_DISABLED_MESSAGE)
    return 1


def _baseline_has_recorded_debt(baseline: dict[str, set[str]]) -> bool:
    return any((allowed_ids for allowed_ids in baseline.values()))


def lint_freeze(root: Path) -> int:
    """Snapshot current lint findings into baselines.json when rules are still empty."""
    from slopgate.lint import __version__
    from slopgate.lint._baseline import baseline_path, load_baseline, save_baseline
    from slopgate.lint._collectors import run_all_collectors

    project_root = discover_project_root(root)
    files = _configured_lint_files(project_root, force_all_scope=True)
    existing = load_baseline()
    if _baseline_has_recorded_debt(existing):
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
