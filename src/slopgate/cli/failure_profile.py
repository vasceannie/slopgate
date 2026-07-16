"""Inspection and reset CLI for aggregate repository failure profiles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

from slopgate._argparse_types import SubparserRegistry
from slopgate.cli.io import string_arg
from slopgate.config import load_config
from slopgate.constants import METADATA_CWD
from slopgate.failure_profile import FailureProfileStore


def add_profile_parser(sub: SubparserRegistry) -> None:
    parser = sub.add_parser("profile", help="Inspect or clear aggregate repo failures")
    profile_sub = cast(
        SubparserRegistry, parser.add_subparsers(dest="profile_action", required=True)
    )
    for action in ("show", "clear", "reset"):
        command = profile_sub.add_parser(action)
        command.set_defaults(func=cmd_profile, profile_action=action)
        _ = command.add_argument("--cwd", default="")


def cmd_profile(args: argparse.Namespace) -> int:
    cwd_text = string_arg(args, METADATA_CWD).strip()
    cwd = Path(cwd_text).expanduser().resolve() if cwd_text else Path.cwd().resolve()
    config = load_config(
        root=cwd, repo_root=cwd, ensure_enrollment=False, ensure_trace=False
    )
    store = FailureProfileStore(
        config.trace_dir, config.repo_root, config.failure_profile
    )
    action = string_arg(args, "profile_action")
    if action in {"clear", "reset"}:
        store.clear()
        payload = {"status": "cleared", "scope_id": store.scope_id}
    else:
        snapshot = store.snapshot()
        payload = {
            "enabled": config.failure_profile.enabled,
            "retention_days": config.failure_profile.retention_days,
            "max_entries": config.failure_profile.max_entries,
            "scope_id": snapshot.scope_id,
            "entries": [entry.to_json() for entry in snapshot.entries],
        }
    print(json.dumps(payload, sort_keys=True))
    return 0
