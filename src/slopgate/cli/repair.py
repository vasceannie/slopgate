"""OpenCode repair-gate commands."""
from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING
from slopgate._argparse_types import SubparserRegistry
from slopgate._types import object_list

from slopgate.config import load_config
from slopgate.state import HookStateCorruptionError, HookStateStore

if TYPE_CHECKING:
    from slopgate.cli.lint.report import LintFiles
    from slopgate.lint._collector_groups.types import CollectorResults


def _store(cwd: str) -> HookStateStore:
    root = Path(cwd).resolve()
    config = load_config(repo_root=root)
    return HookStateStore(config.trace_dir, scope=str(root))


def _string_items(value: object) -> list[str]:
    return [item for item in object_list(value) if isinstance(item, str)]


def _collector_ids_for_rules(rule_ids: Sequence[str]) -> frozenset[str]:
    from slopgate.lint._parity import HOOK_RULE_BASELINE_COUNTERPARTS

    mapped: set[str] = set()
    for rule_id in rule_ids:
        mapped.update(HOOK_RULE_BASELINE_COUNTERPARTS.get(rule_id, ()))
    return frozenset(mapped)


def _locate_repair_path(project: Path, raw: str) -> Path | None:
    """Resolve a recorded repair path to a file inside *project*.

    Every candidate (absolute, relocated, or relative) must resolve to a
    real file that stays inside the project root. Absolute host paths and
    relative ``..`` escapes are rejected rather than remapped.
    """
    project = project.resolve()
    candidate = Path(raw)
    if not candidate.is_absolute():
        located = (project / candidate).resolve()
        return located if located.is_file() and located.is_relative_to(project) else None
    resolved = candidate.resolve()
    if resolved.is_file() and resolved.is_relative_to(project):
        return resolved
    for index in range(len(resolved.parts)):
        relocated = project.joinpath(*resolved.parts[index:]).resolve()
        if relocated.is_file() and relocated.is_relative_to(project):
            return relocated
    return None


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


def _project_lint_files(cwd: Path) -> LintFiles:
    """Return the full project lint inventory with CLI analysis context."""
    from slopgate.cli.lint.commands import discover_project_root
    from slopgate.cli.lint.report import LintFiles
    from slopgate.constants import LINT_SCOPE_ALL
    from slopgate.lint._config import (
        load_config,
        reset_quality_scope,
        set_config,
        set_quality_scope,
    )
    from slopgate.lint._helpers import find_source_files, find_test_files

    project = discover_project_root(cwd)
    scope_token = set_quality_scope(LINT_SCOPE_ALL)
    cfg = load_config(project)
    set_config(cfg)
    try:
        return LintFiles(cfg, find_source_files(), find_test_files())
    finally:
        reset_quality_scope(scope_token)


def _filter_scoped_results(
    results: CollectorResults,
    *,
    collector_ids: frozenset[str],
    recorded_relative: set[str],
) -> CollectorResults:
    """Restrict collector output to targeted collectors and recorded paths."""
    from slopgate.lint._baseline import Violation

    scoped: CollectorResults = []
    for name, violations in results:
        if collector_ids and name not in collector_ids:
            continue
        kept = [
            item
            for item in violations
            if isinstance(item, Violation) and item.relative_path in recorded_relative
        ]
        if kept:
            scoped.append((name, kept))
    return scoped


def _run_scoped_lint(cwd: Path, paths: Sequence[str], rule_ids: Sequence[str]) -> int:
    from slopgate.cli.lint.report import (
        BaselineInputs,
        LintHeader,
        print_collector_results,
        print_lint_header,
    )
    from slopgate.lint import __version__
    from slopgate.lint._baseline import load_baseline
    from slopgate.lint._collectors import run_all_collectors
    from slopgate.lint._helpers import relative_path

    if not paths:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "reason": "repair generation has no recorded paths",
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
    files = _project_lint_files(cwd)
    results = run_all_collectors(files.src_files, files.test_files)
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
        LintHeader(__version__, "repair-verify", files, gate="all")
    )
    return print_collector_results(
        scoped,
        BaselineInputs(stored=load_baseline(), accepted={}),
        gate="all",
        details=False,
        sync_baseline=False,
    )


def cmd_repair_status(args: argparse.Namespace) -> int:
    try:
        state = _store(args.cwd).get_repair_required()
    except HookStateCorruptionError as exc:
        print(json.dumps({"status": "REPAIR_STATE_INVALID", "reason": str(exc)}))
        return 2
    print(json.dumps(state or {"status": "clean"}, sort_keys=True))
    return 0


def cmd_repair_verify(args: argparse.Namespace) -> int:
    store = _store(args.cwd)
    try:
        required = store.get_repair_required()
    except HookStateCorruptionError as exc:
        print(json.dumps({"status": "REPAIR_STATE_INVALID", "reason": str(exc)}))
        return 2
    if required is None:
        print(json.dumps({"status": "clean"}, sort_keys=True))
        return 0
    if required.get("generation") != args.generation:
        print(json.dumps({"status": "generation_mismatch"}, sort_keys=True))
        return 1
    completed = _run_scoped_lint(
        Path(args.cwd).resolve(),
        _string_items(required.get("paths")),
        _string_items(required.get("rule_ids")),
    )
    if completed != 0:
        return completed
    if not store.clear_repair_required(args.generation):
        print(json.dumps({"status": "generation_mismatch"}, sort_keys=True))
        return 1
    print(json.dumps({"status": "cleared", "generation": args.generation}))
    return 0


def add_repair_parsers(sub: SubparserRegistry) -> None:
    repair = sub.add_parser("repair", help="Inspect or verify repair-required state")
    repair_sub = repair.add_subparsers(dest="repair_command", required=True)
    status = repair_sub.add_parser("status", help="Print current repair state")
    status.add_argument("--cwd", default=".")
    status.set_defaults(func=cmd_repair_status)
    verify = repair_sub.add_parser(
        "verify", help="Run clean verification and clear a generation"
    )
    verify.add_argument("--cwd", default=".")
    verify.add_argument("--generation", required=True)
    verify.set_defaults(func=cmd_repair_verify)
