"""Payload and rollout builders for projected lint tests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from slopgate._types import ObjectDict, object_dict

RULE_ID = "QUALITY-PROJECTED-LINT-001"
BAD_LINE = (
    "RESULT = calculate(" + ", ".join(f"value_{index}" for index in range(30)) + ")\n"
)
BAD_TEST = (
    "def test_values() -> None:\n"
    "    assert first\n"
    "    assert second\n"
    "    assert third\n"
    "    assert fourth\n"
)


@dataclass(frozen=True, slots=True)
class BlockingCase:
    platform: str
    event: str
    container_key: str
    decision_key: str
    expected: str


@dataclass(frozen=True, slots=True)
class WriteCase:
    event: str = "PreToolUse"
    session_id: str = "projected-session"
    target: str = "src/app.py"


def configure_rollout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    action: str | None = None,
    enabled: bool | None = None,
) -> Path:
    trace_dir = tmp_path / "trace"
    hook: dict[str, str | bool] = {}
    if action is not None:
        hook["action"] = action
    if enabled is not None:
        hook["enabled"] = enabled
    config: dict[str, str | bool | dict[str, dict[str, dict[str, str | bool]]]] = {
        "trace_dir": str(trace_dir),
        "python_ast_enabled": False,
    }
    if hook:
        config["rule_surfaces"] = {RULE_ID: {"hook": hook}}
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setenv("SLOPGATE_CONFIG", str(config_path))
    return trace_dir


def write_payload(
    repo: Path,
    content: str,
    case: WriteCase = WriteCase(),
) -> ObjectDict:
    return {
        "session_id": case.session_id,
        "cwd": str(repo),
        "hook_event_name": case.event,
        "tool_name": "Write",
        "tool_input": {"file_path": case.target, "content": content},
    }


def edit_payload(repo: Path) -> ObjectDict:
    return {
        "session_id": "projected-edit",
        "cwd": str(repo),
        "hook_event_name": "PreToolUse",
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "src/app.py",
            "old_string": "    return 1\n",
            "new_string": BAD_LINE,
        },
    }


def shell_append_payload(repo: Path) -> ObjectDict:
    return {
        "session_id": "projected-shell",
        "cwd": str(repo),
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {
            "command": "python -c \"open('src/app.py', 'a').write('x = 1\\n')\""
        },
    }


def traced_projected_rule(trace_dir: Path) -> ObjectDict:
    traces = (trace_dir / "rules.jsonl").read_text(encoding="utf-8").splitlines()
    traced = next(
        object_dict(json.loads(line))
        for line in traces
        if object_dict(json.loads(line)).get("rule_id") == RULE_ID
    )
    return traced


def native_blocking_output(result_output: object, case: BlockingCase) -> ObjectDict:
    output = object_dict(result_output)
    if case.container_key:
        output = object_dict(output.get(case.container_key))
    return output


def materialize_projected_file(repo: Path, relative_path: str, content: str) -> None:
    target = repo / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
