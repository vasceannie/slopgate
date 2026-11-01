"""Focused tests for the session mutation tracking rule."""

from __future__ import annotations

import json
from pathlib import Path
from time import time

import pytest

from slopgate.rules.common import SessionMutationTrackingRule

from tests.integration.guard_context_support import context_for_payload

WRITE_PAYLOAD: dict[str, object] = {
    "session_id": "tracking-session",
    "hook_event_name": "PostToolUse",
    "tool_name": "Write",
    "tool_input": {"file_path": "example.py", "content": "value = 1\n"},
}

HOUR_SECONDS = 3600

READ_PAYLOAD: dict[str, object] = {
    "session_id": "tracking-read-session",
    "hook_event_name": "PostToolUse",
    "tool_name": "Read",
    "tool_input": {"file_path": "example.py"},
}


def test_session_mutation_tracking_rule_records_mutating_tool_use(
    tmp_path: Path,
) -> None:
    ctx = context_for_payload(tmp_path, WRITE_PAYLOAD)

    findings = SessionMutationTrackingRule().evaluate(ctx)

    assert findings == [], f"expected no findings, got {findings}"
    assert ctx.state.has_session_mutation("tracking-session"), (
        "expected the mutating tool use to be recorded"
    )


def test_session_mutation_tracking_rule_ignores_read_only_tool_use(
    tmp_path: Path,
) -> None:
    ctx = context_for_payload(tmp_path, READ_PAYLOAD)

    findings = SessionMutationTrackingRule().evaluate(ctx)

    assert findings == [], f"expected no findings, got {findings}"
    assert not ctx.state.has_session_mutation("tracking-read-session"), (
        "expected read-only tool use to leave the session unmarked"
    )


def _state_file(tmp_path: Path) -> Path:
    return tmp_path / ".slopgate" / "trace" / "hook-state.json"


def test_empty_session_id_is_never_recorded(tmp_path: Path) -> None:
    ctx = context_for_payload(tmp_path, {**WRITE_PAYLOAD, "session_id": ""})

    _ = SessionMutationTrackingRule().evaluate(ctx)

    assert not _state_file(tmp_path).exists(), (
        "an id-less mutation must not create a shared session entry"
    )
    assert ctx.state.has_session_mutation(""), (
        "id-less sessions keep the ungated stop guidance"
    )


def test_repeat_mutation_within_refresh_window_skips_rewrite(tmp_path: Path) -> None:
    ctx = context_for_payload(tmp_path, WRITE_PAYLOAD)
    ctx.state.record_session_mutation("tracking-session", "Write")

    ctx.state.record_session_mutation("tracking-session", "Edit")

    state = json.loads(_state_file(tmp_path).read_text(encoding="utf-8"))
    entry = state["session_mutations"]["tracking-session"]
    assert entry["tool"] == "write", f"expected the fresh entry kept, got {entry}"


@pytest.mark.parametrize(
    ("age_seconds", "expected"),
    [(2 * HOUR_SECONDS, True), (25 * HOUR_SECONDS, False)],
    ids=["outlives-generic-ttl", "expires-after-a-day"],
)
def test_session_mutation_uses_day_long_ttl(
    tmp_path: Path, age_seconds: int, expected: bool
) -> None:
    ctx = context_for_payload(tmp_path, WRITE_PAYLOAD)
    entry = {"tool": "write", "timestamp": int(time()) - age_seconds}
    _ = _state_file(tmp_path).write_text(
        json.dumps({"session_mutations": {"tracking-session": entry}}),
        encoding="utf-8",
    )

    marked = ctx.state.has_session_mutation("tracking-session")

    assert marked is expected, f"age {age_seconds}s: expected {expected}, got {marked}"
