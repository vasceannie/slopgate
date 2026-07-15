"""Shared test helpers that are not pytest fixtures."""

from __future__ import annotations

import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import pytest

from slopgate._types import ObjectDict, object_dict, object_list, string_value
from slopgate.constants import METADATA_DECISION, METADATA_PATH
from slopgate.models import EngineResult

BUNDLE_ROOT = Path(__file__).resolve().parents[1]

SKIP_UNIX_ONLY = pytest.mark.skipif(
    sys.platform == "win32",
    reason="Requires Unix path or shell semantics",
)

SKIP_LINUX_ONLY = pytest.mark.skipif(
    sys.platform != "linux",
    reason="Requires Linux scheduler semantics",
)

SKIP_DARWIN_ONLY = pytest.mark.skipif(
    sys.platform != "darwin",
    reason="Requires macOS scheduler semantics",
)

SKIP_WINDOWS_ONLY = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Requires Windows scheduler semantics",
)

# ---------------------------------------------------------------------------
# Fixture type aliases — import in test files to annotate fixture params.
# ---------------------------------------------------------------------------

LoadFixture = Callable[[str], ObjectDict]


@dataclass(frozen=True, slots=True)
class StatsResultSpec:
    """Minimal completed-result finding input for stats tests."""

    event_name: str = "PreToolUse"
    rule_id: str = "GIT-001"
    decision: str = "deny"
    session_id: str = "s1"


def stats_result_entry(spec: StatsResultSpec = StatsResultSpec()) -> ObjectDict:
    """Build a legacy completed-result record for stats compatibility tests."""
    return {
        "timestamp": "2026-04-01T12:00:00+00:00",
        "event_name": spec.event_name,
        "session_id": spec.session_id,
        "tool_name": "Bash",
        "findings": [
            {
                "rule_id": spec.rule_id,
                METADATA_DECISION: spec.decision,
                "severity": "HIGH",
                "message": f"{spec.rule_id} triggered",
                "metadata": {METADATA_PATH: "src/main.py"},
            }
        ],
    }


def pair_counts(mapping: ObjectDict, key: str) -> dict[str, int]:
    """Extract a JSON-compatible list of string/count pairs."""
    counts: dict[str, int] = {}
    for item in object_list(mapping.get(key)):
        pair = object_list(item)
        if len(pair) == 2 and isinstance(pair[0], str) and isinstance(pair[1], int):
            counts[pair[0]] = pair[1]
    return counts


class WriteBuilder(Protocol):
    def __call__(
        self, file_path: str, content: str, cwd: str | None = ...
    ) -> ObjectDict: ...


class BashBuilder(Protocol):
    def __call__(self, command: str, cwd: str | None = ...) -> ObjectDict: ...


class EvaluateFn(Protocol):
    def __call__(
        self,
        payload_dict: ObjectDict,
        platform: str = ...,
    ) -> EngineResult: ...


# ---------------------------------------------------------------------------
# Result accessors
# ---------------------------------------------------------------------------


def require_output(result: EngineResult) -> ObjectDict:
    assert result.output is not None, "Expected structured output, got None"
    return result.output


def hook_output(result: EngineResult) -> ObjectDict:
    assert result.output is not None, "Expected structured output, got None"
    return object_dict(result.output.get("hookSpecificOutput"))


def nested_output(mapping: ObjectDict, key: str) -> ObjectDict:
    raw: object = mapping.get(key, {})
    return object_dict(raw)


def output_string(mapping: ObjectDict, key: str, default: str = "") -> str:
    value = string_value(mapping.get(key))
    return value if value is not None else default


def required_string(mapping: ObjectDict, key: str) -> str:
    value = string_value(mapping.get(key))
    assert value is not None, (
        f"Expected string at key '{key}', got: {mapping.get(key)!r}"
    )
    return value


# ---------------------------------------------------------------------------
# Assertion helpers
# ---------------------------------------------------------------------------


def assert_denied_by(
    result: EngineResult, rule_id: str, msg_fragment: str = ""
) -> None:
    spec = hook_output(result)
    decision = output_string(spec, "permissionDecision") or None
    if decision is None:
        inner = nested_output(spec, "decision")
        decision = output_string(inner, "behavior") or None
        reason = output_string(inner, "message")
    else:
        reason = output_string(spec, "permissionDecisionReason")
    assert decision == "deny", f"Expected deny, got {decision}. Output: {result.output}"
    assert rule_id in reason, f"Expected {rule_id} in reason, got: {reason}"
    if msg_fragment:
        assert msg_fragment.lower() in reason.lower(), (
            f"Expected '{msg_fragment}' in reason"
        )


def assert_asked_by(result: EngineResult, rule_id: str, msg_fragment: str = "") -> None:
    spec = hook_output(result)
    decision = output_string(spec, "permissionDecision") or None
    if decision is None:
        inner = nested_output(spec, "decision")
        decision = output_string(inner, "behavior") or None
        reason = output_string(inner, "message")
    else:
        reason = output_string(spec, "permissionDecisionReason")
    assert decision == "ask", f"Expected ask, got {decision}. Output: {result.output}"
    assert rule_id in reason, f"Expected {rule_id} in reason, got: {reason}"
    if msg_fragment:
        assert msg_fragment.lower() in reason.lower(), (
            f"Expected '{msg_fragment}' in reason"
        )


def assert_blocked(result: EngineResult, rule_id: str = "") -> None:
    output = require_output(result)
    assert output_string(output, "decision") == "block", (
        f"Expected block, got: {result.output}"
    )
    if rule_id:
        reason = output_string(output, "reason")
        assert rule_id in reason, f"Expected {rule_id} in reason, got: {reason}"


def assert_not_denied(result: EngineResult) -> None:
    if result.output is None:
        return
    spec = hook_output(result)
    decision = output_string(spec, "permissionDecision") or None
    assert decision != "deny", (
        f"Expected no deny but got: {output_string(spec, 'permissionDecisionReason')}"
    )


def finding_ids(result: EngineResult) -> set[str]:
    return {f.rule_id for f in result.findings}


def pretool_delete_payload(cwd: Path, file_path: str) -> ObjectDict:
    return {
        "session_id": "t",
        "cwd": str(cwd),
        "hook_event_name": "PreToolUse",
        "tool_name": "Delete",
        "tool_input": {"file_path": file_path},
    }
