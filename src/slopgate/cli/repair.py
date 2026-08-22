"""OpenCode repair-gate commands."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from slopgate._argparse_types import SubparserRegistry

from slopgate.config import load_config
from slopgate.state import HookStateCorruptionError, HookStateStore


def _lint_check_command() -> list[str]:
    return [sys.executable, "-m", "slopgate", "lint", "check"]


def _run_lint_check(cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        _lint_check_command(),
        cwd=cwd,
        check=False,
        text=True,
    )


def _store(cwd: str) -> HookStateStore:
    root = Path(cwd).resolve()
    config = load_config(repo_root=root)
    return HookStateStore(config.trace_dir, scope=str(root))


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
    completed = _run_lint_check(Path(args.cwd).resolve())
    if completed.returncode != 0:
        return completed.returncode
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
