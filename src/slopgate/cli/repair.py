"""OpenCode repair-gate commands."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path
from slopgate._argparse_types import SubparserRegistry
from slopgate._types import object_list

from slopgate.config import load_config
from slopgate.state import HookStateCorruptionError, HookStateStore


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
    project = project.resolve()
    candidate = Path(raw)
    if not candidate.is_absolute():
        located = (project / candidate).resolve()
        return located if located.is_file() else None
    resolved = candidate.resolve()
    if resolved.is_file() and resolved.is_relative_to(project):
        return resolved
    for index in range(len(resolved.parts)):
        relocated = project.joinpath(*resolved.parts[index:])
        if relocated.is_file():
            return relocated.resolve()
    return None


def _resolve_repair_files(
    cwd: Path, paths: Sequence[str]
) -> tuple[list[Path], list[Path]]:
    from slopgate.cli.lint.commands import discover_project_root
    from slopgate.lint._config import load_config as load_lint_config
    from slopgate.lint._config import set_config

    project = discover_project_root(cwd)
    cfg = load_lint_config(project)
    set_config(cfg)
    test_roots = tuple(root.resolve() for root in cfg.test_roots)
    src_files: list[Path] = []
    test_files: list[Path] = []
    for raw in paths:
        path = _locate_repair_path(project, raw)
        if path is None:
            continue
        if any(path.is_relative_to(root) for root in test_roots):
            test_files.append(path)
            continue
        src_files.append(path)
    return src_files, test_files


def _run_scoped_lint(cwd: Path, paths: Sequence[str], rule_ids: Sequence[str]) -> int:
    from slopgate.cli.lint.report import (
        BaselineInputs,
        LintFiles,
        LintHeader,
        print_collector_results,
        print_lint_header,
    )
    from slopgate.lint import __version__
    from slopgate.lint._baseline import load_baseline
    from slopgate.lint._collectors import CollectorRunOptions, run_all_collectors
    from slopgate.lint._config import get_config

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
    src_files, test_files = _resolve_repair_files(cwd, paths)
    results = run_all_collectors(
        src_files,
        test_files,
        CollectorRunOptions(
            persist_index=False,
            use_index=False,
            build_constants=False,
        ),
    )
    collector_ids = _collector_ids_for_rules(rule_ids)
    if collector_ids:
        results = [
            (name, violations)
            for name, violations in results
            if name in collector_ids
        ]
    files = LintFiles(get_config(), src_files, test_files)
    print_lint_header(LintHeader(__version__, "repair-verify", files, gate="new"))
    return print_collector_results(
        results,
        BaselineInputs(stored=load_baseline(), accepted={}),
        gate="new",
        details=False,
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
