from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from slopgate._types import object_dict, string_value
from slopgate.engine import evaluate_payload
from slopgate.models import EngineResult
from slopgate.rules.python_ast._pytest_asyncio_messages import PYTEST_ASYNCIO_TEMPLATE

BUNDLE_ROOT = Path(__file__).resolve().parents[1]
UNMARKED_CLIENT_TEST = """
async def test_fetches_client(client):
    result = await client.fetch()
    assert result.ok, f"expected ok result, got {result!r}"
"""


def _write_payload(path: str, code: str, cwd: Path | None = None) -> dict[str, object]:
    return {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": path, "content": code},
        "cwd": str(cwd or BUNDLE_ROOT),
    }


def _repo_root(tmp_path: Path, pytest_config: str = "", *, config_name: str = "pytest.ini") -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / "slopgate.toml").write_text("[slopgate]\nenabled = true\n", encoding="utf-8")
    if pytest_config:
        _ = (repo / config_name).write_text(pytest_config, encoding="utf-8")
    return repo


def _evaluate_test_client(repo: Path, code: str) -> EngineResult:
    return evaluate_payload(_write_payload("tests/test_client.py", code, repo))


def _write_pytest_mode(repo: Path, mode: str) -> None:
    _ = (repo / "pytest.ini").write_text(f"[pytest]\nasyncio_mode = {mode}\n", encoding="utf-8")


def _permission_decision(result: EngineResult) -> str | None:
    assert result.output is not None, "expected hook output"
    specific = object_dict(result.output.get("hookSpecificOutput"))
    decision = string_value(specific.get("permissionDecision"))
    if decision is not None:
        return decision
    inner = object_dict(specific.get("decision"))
    return string_value(inner.get("behavior"))


def _permission_reason(result: EngineResult) -> str:
    assert result.output is not None, "expected hook output"
    specific = object_dict(result.output.get("hookSpecificOutput"))
    reason = string_value(specific.get("permissionDecisionReason"))
    if reason is not None:
        return reason
    inner = object_dict(specific.get("decision"))
    return string_value(inner.get("message")) or ""


def _assert_denied_by_pytest_asyncio(result: EngineResult) -> str:
    assert _permission_decision(result) == "deny"
    reason = _permission_reason(result)
    assert "PY-TEST-005" in reason
    assert "pytest-asyncio" in reason
    return reason


def _pytest_asyncio_denials(result: EngineResult) -> list[object]:
    return [
        finding
        for finding in result.findings
        if finding.rule_id == "PY-TEST-005" and finding.decision in {"deny", "block"}
    ]

# Exported test support used by split test modules.
__all__ = ('BUNDLE_ROOT', 'EngineResult', 'PYTEST_ASYNCIO_TEMPLATE', 'Path', 'UNMARKED_CLIENT_TEST', '_assert_denied_by_pytest_asyncio', '_evaluate_test_client', '_permission_decision', '_permission_reason', '_pytest_asyncio_denials', '_repo_root', '_write_payload', '_write_pytest_mode', 'evaluate_payload', 'object_dict', 'pytest', 'string_value', 'subprocess', 'sys', 'textwrap')
