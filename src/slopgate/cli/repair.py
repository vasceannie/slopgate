"""OpenCode repair-gate commands."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING
from slopgate._argparse_types import SubparserRegistry
from slopgate._types import ObjectDict, object_dict_list

from slopgate.config import load_config
from slopgate.constants import (
    LINT_SCOPE_ALL,
    METADATA_PATH,
    REPAIR_TARGET_ERROR,
    RULE_ID_KEY,
    WORKTREE_KEY,
)
from slopgate.state import HookStateCorruptionError, HookStateStore

if TYPE_CHECKING:
    from slopgate.lint._collector_groups.types import CollectorResults


def _store(cwd: str, worktree: str | None = None) -> tuple[HookStateStore, Path]:
    from slopgate.cli.lint.commands import discover_project_root

    path_base = Path(cwd).resolve()
    if isinstance(worktree, str) and worktree.strip():
        worktree_path = Path(worktree)
        if not worktree_path.is_absolute():
            raise ValueError("repair worktree must be an absolute path")
        root = worktree_path.resolve()
    else:
        root = discover_project_root(path_base)
    if not path_base.is_relative_to(root):
        raise ValueError("repair cwd is outside the requested worktree")
    config = load_config(repo_root=root)
    store = HookStateStore(config.trace_dir, scope=str(root), path_base=path_base)
    return store, root


def _validate_repair_worktree(required: ObjectDict | None, root: Path) -> None:
    if required is None:
        return
    recorded = required.get(WORKTREE_KEY)
    if recorded != str(root):
        raise ValueError("repair state worktree does not match requested worktree")


def _collector_ids_for_rules(rule_ids: Sequence[str]) -> frozenset[str]:
    from slopgate.lint._parity import HOOK_RULE_BASELINE_COUNTERPARTS

    mapped: set[str] = set()
    for rule_id in rule_ids:
        mapped.update(HOOK_RULE_BASELINE_COUNTERPARTS.get(rule_id, ()))
    return frozenset(mapped)


def _locate_repair_path(project: Path, raw: str) -> Path | None:
    """Resolve a recorded repair path to a file inside *project*.

    Every absolute or relative candidate must resolve to a real file that
    stays inside the project root. Foreign host paths, symlink escapes, and
    relative parent escapes are rejected rather than remapped.
    """
    project = project.resolve()
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = project / candidate
    resolved = candidate.resolve()
    if resolved.is_file() and resolved.is_relative_to(project):
        return resolved
    return None


def _repair_scope(
    targets: Sequence[ObjectDict],
) -> tuple[list[str], list[str], list[str]]:
    paths: list[str] = []
    rule_ids: list[str] = []
    invalid: list[str] = []
    for target in targets:
        rule_id = target.get(RULE_ID_KEY)
        path = target.get(METADATA_PATH)
        error = target.get(REPAIR_TARGET_ERROR)
        if not isinstance(rule_id, str) or not rule_id:
            invalid.append("repair target has no rule id")
            continue
        rule_ids.append(rule_id)
        if isinstance(error, str) and error:
            invalid.append(f"{rule_id}: {error}")
            continue
        if not isinstance(path, str) or not path:
            invalid.append(f"{rule_id}: repair target has no canonical path")
            continue
        paths.append(path)
    return paths, rule_ids, invalid


def _resolve_repair_files(
    cwd: Path, paths: Sequence[str]
) -> tuple[list[Path], list[Path], list[str]]:
    from slopgate.cli.lint.commands import discover_project_root
    from slopgate.lint._config import load_config
    from slopgate.lint._config import set_config

    project = discover_project_root(cwd)
    cfg = load_config(project)
    set_config(cfg)
    test_roots = tuple(root.resolve() for root in cfg.test_roots)
    src_files: list[Path] = []
    test_files: list[Path] = []
    unresolved: list[str] = []
    for raw in paths:
        path = _locate_repair_path(project, raw)
        if path is None:
            unresolved.append(raw)
            continue
        if any(path.is_relative_to(root) for root in test_roots):
            test_files.append(path)
            continue
        src_files.append(path)
    return src_files, test_files, unresolved


def _filter_scoped_results(
    results: CollectorResults,
    *,
    collector_ids: frozenset[str],
    recorded_relative: set[str],
) -> CollectorResults:
    """Restrict collector output to targeted collectors and recorded paths."""
    scoped: CollectorResults = []
    for name, violations in results:
        if collector_ids and name not in collector_ids:
            continue
        kept = [item for item in violations if item.relative_path in recorded_relative]
        if kept:
            scoped.append((name, kept))
    return scoped


def _print_scoped_lint(
    src_files: list[Path], test_files: list[Path], rule_ids: Sequence[str]
) -> int:
    from slopgate.cli.lint.report import (
        BaselineInputs,
        CollectorReportOptions,
        LintFiles,
        LintHeader,
        print_collector_results,
        print_lint_header,
    )
    from slopgate.lint import __version__
    from slopgate.lint._baseline import load_baseline
    from slopgate.lint._collectors import run_all_collectors
    from slopgate.lint._config import get_config
    from slopgate.lint._helpers import relative_path

    files = LintFiles(get_config(), src_files, test_files)
    results = run_all_collectors(src_files, test_files)
    collector_ids = _collector_ids_for_rules(rule_ids)
    recorded_relative = {relative_path(path) for path in [*src_files, *test_files]}
    if src_files:
        recorded_relative.add("<project>")
    scoped = _filter_scoped_results(
        results,
        collector_ids=collector_ids,
        recorded_relative=recorded_relative,
    )
    print_lint_header(
        LintHeader(__version__, "repair-verify", files, gate=LINT_SCOPE_ALL)
    )
    return print_collector_results(
        scoped,
        BaselineInputs(stored=load_baseline(), accepted={}),
        CollectorReportOptions(gate=LINT_SCOPE_ALL, sync_baseline=False),
    )


def _run_scoped_lint(cwd: Path, targets: Sequence[ObjectDict]) -> int:
    paths, rule_ids, invalid = _repair_scope(targets)
    if invalid:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "reason": "repair generation has unverifiable targets",
                    "targets": invalid,
                }
            )
        )
        return 1
    if not paths:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "reason": "legacy repair generation has no associated targets",
                }
            )
        )
        return 1
    src_files, test_files, unresolved = _resolve_repair_files(cwd, paths)
    if unresolved:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "reason": "recorded repair path(s) do not resolve to files",
                    "paths": sorted(unresolved),
                }
            )
        )
        return 1
    return _print_scoped_lint(src_files, test_files, rule_ids)


def cmd_repair_status(args: argparse.Namespace) -> int:
    try:
        store, root = _store(args.cwd, getattr(args, "worktree", None))
        state = store.get_repair_required()
        _validate_repair_worktree(state, root)
    except (HookStateCorruptionError, ValueError) as exc:
        print(json.dumps({"status": "REPAIR_STATE_INVALID", "reason": str(exc)}))
        return 2
    print(json.dumps(state or {"status": "clean"}, sort_keys=True))
    return 0


def cmd_repair_verify(args: argparse.Namespace) -> int:
    try:
        store, root = _store(args.cwd, getattr(args, "worktree", None))
        required = store.get_repair_required()
        _validate_repair_worktree(required, root)
    except (HookStateCorruptionError, ValueError) as exc:
        print(json.dumps({"status": "REPAIR_STATE_INVALID", "reason": str(exc)}))
        return 2
    if required is None:
        print(json.dumps({"status": "clean"}, sort_keys=True))
        return 0
    if required.get("generation") != args.generation:
        print(json.dumps({"status": "generation_mismatch"}, sort_keys=True))
        return 1
    completed = _run_scoped_lint(root, object_dict_list(required.get("targets")))
    if completed != 0:
        return completed
    if not store.clear_repair_required(args.generation):
        print(json.dumps({"status": "generation_mismatch"}, sort_keys=True))
        return 1
    print(json.dumps({"status": "cleared", "generation": args.generation}))
    return 0


def _add_repair_scope_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--cwd", default=".")
    parser.add_argument("--worktree")


def add_repair_parsers(sub: SubparserRegistry) -> None:
    repair = sub.add_parser("repair", help="Inspect or verify repair-required state")
    repair_sub = repair.add_subparsers(dest="repair_command", required=True)
    status = repair_sub.add_parser("status", help="Print current repair state")
    _add_repair_scope_arguments(status)
    status.set_defaults(func=cmd_repair_status)
    verify = repair_sub.add_parser(
        "verify", help="Run clean verification and clear a generation"
    )
    _add_repair_scope_arguments(verify)
    verify.add_argument("--generation", required=True)
    verify.set_defaults(func=cmd_repair_verify)
