"""Behavior contracts for completed-result trace schema helpers."""

from __future__ import annotations

from pathlib import Path

from hypothesis import HealthCheck, given, settings, strategies

from slopgate._types import ObjectDict
from slopgate.context import HookContext, build_context
from slopgate.engine._retry import attempt_fingerprint
from slopgate.engine._trace_schema import (
    TraceIdentity,
    completed_trace_fields,
    start_trace_fields,
    trace_identity,
)
from slopgate.models import EngineResult


def _write_context(
    tmp_path: Path, content: str, operation_id: str = "call-1"
) -> HookContext:
    payload: ObjectDict = {
        "session_id": "session-1",
        "cwd": str(tmp_path),
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_call_id": operation_id,
        "tool_input": {"file_path": "src/app.py", "content": content},
    }
    return build_context(payload)


def _trace_projection(ctx: HookContext) -> ObjectDict:
    identity: TraceIdentity = trace_identity(ctx, str(ctx.cwd))
    start = start_trace_fields(ctx, identity)
    completed = completed_trace_fields(
        ctx,
        EngineResult(event_name=ctx.event_name, findings=[], output=None, errors=[]),
        identity,
    )
    return {
        "same_evaluation_id": start["evaluation_id"] == completed["evaluation_id"],
        "operation_id": completed["operation_id"],
        "correlation_confidence": completed["correlation_confidence"],
        "event_outcome": completed["event_outcome"],
        "tool_outcome": completed["tool_outcome"],
        "repair_plan_state": completed["repair_plan_state"],
    }


def test_trace_schema_helpers_share_identity_and_classify_clean_result(
    tmp_path: Path,
) -> None:
    ctx = _write_context(tmp_path, "value = 1\n")

    assert _trace_projection(ctx) == {
        "same_evaluation_id": True,
        "operation_id": "call-1",
        "correlation_confidence": "exact",
        "event_outcome": "passed_clean",
        "tool_outcome": "unknown",
        "repair_plan_state": "none",
    }, "Trace helpers must preserve identity and classify observed evidence"


@given(strategies.text(min_size=1, max_size=80))
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_attempt_fingerprint_is_deterministic_for_same_edit(
    tmp_path: Path,
    content: str,
) -> None:
    first = attempt_fingerprint(_write_context(tmp_path, content))
    second = attempt_fingerprint(_write_context(tmp_path, content))

    assert (first is not None, first == second) == (True, True), (
        "The existing mutation fingerprint must be stable for identical attempts"
    )
