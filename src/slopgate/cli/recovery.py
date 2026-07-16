"""CLI surface for structured retry recovery evidence."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

from slopgate._argparse_types import SubparserRegistry
from slopgate.cli.first_write_contract import record_parser
from slopgate.cli.io import string_arg
from slopgate.config import load_config, resolve_repo_root
from slopgate.constants import METADATA_CWD
from slopgate.state import (
    HookStateStore,
    RecoveryEvidenceDraft,
    RecoveryEvidenceError,
    RecoveryEvidenceRecord,
)


@dataclass(frozen=True, slots=True)
class _RecoveryFailure:
    code: str


def _add_recovery_parser(sub: SubparserRegistry) -> None:
    parser = record_parser(
        sub,
        "recovery",
        "Record structured evidence to unlock a semantic retry",
        "Record changed-design evidence for the active semantic retry lock",
    )
    parser.set_defaults(func=_cmd_recovery)
    for option in (
        "--violated-invariant",
        "--previous-design-failure",
        "--new-design",
    ):
        _ = parser.add_argument(option, required=True)


def _recovery_draft(
    args: argparse.Namespace, cwd: Path
) -> RecoveryEvidenceDraft | None:
    values = {
        "session_id": string_arg(args, "session_id").strip(),
        "violated_invariant": string_arg(args, "violated_invariant").strip(),
        "previous_design_failure": string_arg(args, "previous_design_failure").strip(),
        "new_design": string_arg(args, "new_design").strip(),
        "verification": string_arg(args, "verification").strip(),
    }
    if not all(values.values()):
        return None
    repo_root = resolve_repo_root(cwd) or cwd
    return RecoveryEvidenceDraft(
        session_id=values["session_id"],
        repo_root=str(repo_root.resolve(strict=False)),
        violated_invariant=values["violated_invariant"],
        previous_design_failure=values["previous_design_failure"],
        new_design=values["new_design"],
        verification=values["verification"],
    )


def _record_recovery(
    store: HookStateStore, draft: RecoveryEvidenceDraft
) -> RecoveryEvidenceRecord | _RecoveryFailure:
    try:
        return store.record_recovery_evidence(draft)
    except RecoveryEvidenceError as exc:
        return _RecoveryFailure(exc.code)


def _cmd_recovery(args: argparse.Namespace) -> int:
    cwd = Path(string_arg(args, METADATA_CWD, ".")).expanduser().resolve()
    draft = _recovery_draft(args, cwd)
    if draft is None:
        print("recovery evidence fields must be non-empty", file=sys.stderr)
        return 2
    config = load_config(
        root=cwd, repo_root=cwd, ensure_enrollment=False, ensure_trace=True
    )
    result = _record_recovery(HookStateStore(config.trace_dir), draft)
    match result:
        case RecoveryEvidenceRecord():
            print(
                json.dumps(
                    {
                        "status": "recorded",
                        "target_count": len(result.target_paths),
                        "rule_count": len(result.locked_rules),
                        "created_at": result.created_at,
                        "schema_version": result.schema_version,
                    },
                    sort_keys=True,
                )
            )
            return 0
        case _RecoveryFailure(code=code):
            print(f"recovery evidence rejected: {code}", file=sys.stderr)
            return 2


add_recovery_parser = _add_recovery_parser
cmd_recovery = _cmd_recovery
