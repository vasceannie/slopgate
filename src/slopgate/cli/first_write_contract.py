"""CLI surface for recording first-write contracts."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from slopgate._types import object_list
from slopgate._argparse_types import SubparserRegistry
from slopgate.cli.io import string_arg
from slopgate.config import load_config
from slopgate.constants import METADATA_CWD
from slopgate.state import (
    FIRST_WRITE_RISK_MAX,
    FIRST_WRITE_RISK_MIN,
    FirstWriteContractDraft,
    HookStateStore,
    normalize_contract_target,
)


def _record_parser(
    sub: SubparserRegistry,
    name: str,
    help_text: str,
    description: str,
) -> argparse.ArgumentParser:
    parser = sub.add_parser(name, help=help_text, description=description)
    _ = parser.add_argument(f"{name}_action", choices=("record",))
    _ = parser.add_argument("--session-id", required=True)
    _ = parser.add_argument("--verification", required=True)
    _ = parser.add_argument("--cwd", default=".")
    return parser


record_parser = _record_parser


def _add_contract_parser(sub: SubparserRegistry) -> None:
    parser = _record_parser(
        sub,
        "contract",
        "Record a state-backed first-write contract",
        "Record structured design evidence before the first edit to a target",
    )
    parser.set_defaults(func=_cmd_contract)
    for option in (
        "--target",
        "--operation",
        "--reuse",
        "--stable-behavior",
        "--design-response",
    ):
        _ = parser.add_argument(option, required=True)
    _ = parser.add_argument("--risk", action="append", required=True)


def _contract_draft(
    args: argparse.Namespace, cwd: Path, risks: tuple[str, ...]
) -> FirstWriteContractDraft | None:
    (
        session_id,
        target,
        operation,
        reuse,
        stable_behavior,
        design_response,
        verification,
    ) = (
        string_arg(args, field).strip()
        for field in (
            "session_id",
            "target",
            "operation",
            "reuse",
            "stable_behavior",
            "design_response",
            "verification",
        )
    )
    if not all(
        (
            session_id,
            target,
            operation,
            reuse,
            stable_behavior,
            design_response,
            verification,
        )
    ):
        return None
    return FirstWriteContractDraft(
        session_id=session_id,
        target=normalize_contract_target(target, cwd),
        operation=operation,
        reuse_convention=reuse,
        stable_behavior_api=stable_behavior,
        predicted_risks=risks,
        design_response=design_response,
        focused_verification=verification,
    )


def _cmd_contract(args: argparse.Namespace) -> int:
    risks = tuple(
        item.strip()
        for item in object_list(getattr(args, "risk", None))
        if isinstance(item, str) and item.strip()
    )
    if not FIRST_WRITE_RISK_MIN <= len(risks) <= FIRST_WRITE_RISK_MAX:
        print(
            f"first-write contract requires {FIRST_WRITE_RISK_MIN}-{FIRST_WRITE_RISK_MAX} predicted risks",
            file=sys.stderr,
        )
        return 2
    cwd = Path(string_arg(args, METADATA_CWD, ".")).expanduser().resolve()
    draft = _contract_draft(args, cwd, risks)
    if draft is None:
        print("first-write contract fields must be non-empty", file=sys.stderr)
        return 2
    config = load_config(
        root=cwd, repo_root=cwd, ensure_enrollment=False, ensure_trace=True
    )
    record = HookStateStore(config.trace_dir).record_first_write_contract(draft)
    payload = asdict(record)
    payload.update(status="recorded", risk_count=len(risks))
    print(
        json.dumps(
            payload,
            sort_keys=True,
        )
    )
    return 0


add_contract_parser = _add_contract_parser
cmd_contract = _cmd_contract
