"""Shared builders for first-write contract tests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from slopgate.cli import main
from slopgate.engine import evaluate_payload
from slopgate.models import EngineResult


RULE_ID = "WORKFLOW-FIRST-WRITE-001"
RISKS = ("compatibility", "normalization", "consumption")


@dataclass(frozen=True, slots=True)
class BlockingCase:
    platform: str
    event: str
    expected_key: str
    expected_value: str


@dataclass(frozen=True, slots=True)
class EditCase:
    event: str = "PreToolUse"
    session_id: str = "session-a"
    target: str = "src/app.py"
    tool_name: str = "Edit"


def configure_contract_test(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    action: str | None = None,
    enabled: bool | None = None,
) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    (repo / "slopgate.toml").write_text("[slopgate]\nenabled = true\n")
    trace_dir = tmp_path / "trace"
    hook: dict[str, object] = {}
    if action is not None:
        hook["action"] = action
    if enabled is not None:
        hook["enabled"] = enabled
    config: dict[str, object] = {"trace_dir": str(trace_dir)}
    if hook:
        config["rule_surfaces"] = {RULE_ID: {"hook": hook}}
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setenv("SLOPGATE_CONFIG", str(config_path))
    return repo, trace_dir


def contract_record_args(
    repo: Path,
    *,
    target: str = "src/app.py",
    session_id: str = "session-a",
    risks: tuple[str, ...] = RISKS,
) -> list[str]:
    args = [
        "contract",
        "record",
        "--session-id",
        session_id,
        "--target",
        target,
        "--operation",
        "Edit",
        "--reuse",
        "existing state facade and fixture convention",
        "--stable-behavior",
        "preserve public constructors and hook output shapes",
    ]
    for risk in risks:
        args.extend(("--risk", risk))
    args.extend(
        (
            "--design-response",
            "add one locked state section and one repo-strict rule",
            "--verification",
            "run focused state, rule, and CLI tests",
            "--cwd",
            str(repo),
        )
    )
    return args


def edit_payload(repo: Path, case: EditCase = EditCase()) -> dict[str, object]:
    return {
        "session_id": case.session_id,
        "cwd": str(repo),
        "hook_event_name": case.event,
        "tool_name": case.tool_name,
        "tool_input": {
            "file_path": case.target,
            "old_string": "old",
            "new_string": "new",
        },
        "tool_response": {"success": True, "filePath": case.target},
    }


def record_contract(
    repo: Path,
    capsys: pytest.CaptureFixture[str],
    *,
    target: str = "src/app.py",
    session_id: str = "session-a",
) -> int:
    exit_code = main(contract_record_args(repo, target=target, session_id=session_id))
    _ = capsys.readouterr()
    return exit_code


def evaluate_edit_cases(
    repo: Path,
    *cases: EditCase,
    platform: str = "claude",
) -> list[EngineResult]:
    return [
        evaluate_payload(edit_payload(repo, case), platform=platform) for case in cases
    ]
