"""Shared non-fixture helpers for hook state spec tests."""

from __future__ import annotations

__all__ = [
    "Mapping",
    "Path",
    "ObjectDict",
    "object_dict",
    "evaluate_payload",
    "EngineResult",
    "RuleFinding",
    "HookStateStore",
    "BUNDLE_ROOT",
    "_RESOURCES",
    "InspectableHookStateStore",
    "config_with_enabled_rules",
    "enable_thin_wrapper_rule",
    "enable_loop_rules",
    "ensure_enrolled",
    "read_payload",
    "bash_payload",
    "grep_payload",
    "posttool_payload",
    "_THIN_WRAPPER_CODE",
    "_thin_wrapper_payload",
    "_evaluate_thin_wrapper_hit",
    "evaluate_thin_wrapper_hits",
    "run_thin_wrapper_subprocess_hit",
    "require_subprocess_finding",
    "repeat_tracking_repair_sequence",
    "_SubprocessFinding",
    "_SubprocessResult",
    "_normalize_subprocess_result",
    "_python_subprocess_env",
    "_start_full_read_record_subprocess",
    "assert_loop_steering_metadata",
    "assert_repeat_counts",
    "collect_process_failures",
    "finding",
    "missing_full_read_records",
    "require_finding",
    "run_payload_in_subprocess",
    "start_full_read_record_processes",
]




import json
from collections.abc import Mapping
from pathlib import Path

import pytest
from slopgate._types import ObjectDict, object_dict
from slopgate.engine import evaluate_payload
from slopgate.models import EngineResult, RuleFinding
from slopgate.state import HookStateStore
from tests.support import BUNDLE_ROOT

_RESOURCES = BUNDLE_ROOT / "src" / "slopgate" / "resources"


class InspectableHookStateStore(HookStateStore):
    def full_read_key(self, session_id: str, path: str) -> str:
        return self._full_read_key(session_id, path)

    def save_state_for_test(self, state: Mapping[str, object]) -> None:
        self._save_state(state)

    @property
    def ttl_seconds(self) -> int:
        return self._TTL_SECONDS

    def load_state_for_test(self) -> ObjectDict:
        return object_dict(self._load_state())


def config_with_enabled_rules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *rule_ids: str
) -> None:
    (tmp_path / "slopgate.toml").write_text("[slopgate]\nenabled = true\n")
    raw = json.loads((_RESOURCES / "defaults.json").read_text(encoding="utf-8"))
    enabled = dict(raw.get("enabled_rules", {}))
    for rule_id in rule_ids:
        enabled[rule_id] = True
    raw["enabled_rules"] = enabled
    config_path = tmp_path / "spec-config.json"
    config_path.write_text(json.dumps(raw), encoding="utf-8")
    monkeypatch.setenv("SLOPGATE_CONFIG", str(config_path))


def enable_thin_wrapper_rule(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_with_enabled_rules(tmp_path, monkeypatch, "PY-CODE-013")


def enable_loop_rules(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config_with_enabled_rules(tmp_path, monkeypatch, "PY-CODE-013", "PY-CODE-009")


def ensure_enrolled(cwd: str) -> None:
    root = Path(cwd)
    marker = root / "slopgate.toml"
    if not marker.exists():
        marker.write_text("[slopgate]\nenabled = true\n", encoding="utf-8")


def read_payload(
    file_path: str,
    *,
    cwd: str,
    session_id: str = "spec-session",
    offset: int | None = None,
    limit: int | None = None,
) -> dict[str, object]:
    ensure_enrolled(cwd)
    tool_input: dict[str, object] = {"file_path": file_path}
    if offset is not None:
        tool_input["offset"] = offset
    if limit is not None:
        tool_input["limit"] = limit
    return {
        "session_id": session_id,
        "cwd": cwd,
        "hook_event_name": "PreToolUse",
        "tool_name": "Read",
        "tool_input": tool_input,
    }


def bash_payload(
    command: str,
    *,
    cwd: str,
    session_id: str = "spec-session",
) -> dict[str, object]:
    ensure_enrolled(cwd)
    return {
        "session_id": session_id,
        "cwd": cwd,
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }


def grep_payload(
    query: str,
    *,
    cwd: str,
    session_id: str = "spec-session",
) -> dict[str, object]:
    ensure_enrolled(cwd)
    return {
        "session_id": session_id,
        "cwd": cwd,
        "hook_event_name": "PreToolUse",
        "tool_name": "Grep",
        "tool_input": {"query": query, "path": "src"},
    }


def posttool_payload(
    *,
    cwd: Path,
    rel_path: str,
    code: str,
    session_id: str = "spec-session",
) -> dict[str, object]:
    ensure_enrolled(str(cwd))
    target = cwd / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(code, encoding="utf-8")
    return {
        "session_id": session_id,
        "cwd": str(cwd),
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": rel_path, "content": code},
        "tool_response": {"filePath": rel_path, "success": True},
    }


_THIN_WRAPPER_CODE = "def get_all_users():\n    return UserRepository.find_all()\n"


def _thin_wrapper_payload(
    cwd: Path, session_id: str = "repeat-session"
) -> dict[str, object]:
    return posttool_payload(
        cwd=cwd,
        rel_path="src/thin.py",
        code=_THIN_WRAPPER_CODE,
        session_id=session_id,
    )


def _evaluate_thin_wrapper_hit(
    cwd: Path, session_id: str = "repeat-session"
) -> EngineResult:
    return evaluate_payload(_thin_wrapper_payload(cwd, session_id))


def evaluate_thin_wrapper_hits(
    cwd: Path, count: int, session_id: str = "repeat-session"
) -> list[EngineResult]:
    return [_evaluate_thin_wrapper_hit(cwd, session_id) for _ in range(count)]


def run_thin_wrapper_subprocess_hit(
    cwd: Path, session_id: str = "repeat-session"
) -> _SubprocessResult:
    return run_payload_in_subprocess(_thin_wrapper_payload(cwd, session_id))


def require_subprocess_finding(
    rule_id: str, result: _SubprocessResult
) -> _SubprocessFinding:
    return next(item for item in result["findings"] if item["rule_id"] == rule_id)


def repeat_tracking_repair_sequence(cwd: Path) -> tuple[EngineResult, EngineResult]:
    thin_wrapper = "def get_all_users():\n    return UserRepository.find_all()\n"
    repaired_code = (
        "def get_all_users():\n"
        "    users = UserRepository.find_all()\n"
        "    return users\n"
    )
    session_id = "repeat-session"
    rel_path = "src/thin.py"
    _ = evaluate_payload(
        posttool_payload(
            cwd=cwd,
            rel_path=rel_path,
            code=thin_wrapper,
            session_id=session_id,
        )
    )
    _ = evaluate_payload(
        posttool_payload(
            cwd=cwd,
            rel_path=rel_path,
            code=thin_wrapper,
            session_id=session_id,
        )
    )
    repaired = evaluate_payload(
        posttool_payload(
            cwd=cwd,
            rel_path=rel_path,
            code=repaired_code,
            session_id=session_id,
        )
    )
    repeated_after_repair = evaluate_payload(
        posttool_payload(
            cwd=cwd,
            rel_path=rel_path,
            code=thin_wrapper,
            session_id=session_id,
        )
    )
    return repaired, repeated_after_repair

from tests.hook_state_subprocess_support import (
    _SubprocessFinding,
    _SubprocessResult,
    _normalize_subprocess_result,
    _python_subprocess_env,
    _start_full_read_record_subprocess,
    assert_loop_steering_metadata,
    assert_repeat_counts,
    collect_process_failures,
    finding,
    missing_full_read_records,
    require_finding,
    run_payload_in_subprocess,
    start_full_read_record_processes,
)
