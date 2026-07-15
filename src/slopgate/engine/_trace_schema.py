"""Completed-result trace schema and deterministic outcome classification."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final
from uuid import uuid4

from slopgate._types import ObjectDict, bool_value, object_dict
from slopgate.constants import (
    ASK,
    BLOCK,
    DENY,
    PERMISSION_REQUEST,
    POST_TOOL_USE,
    PRE_TOOL_USE,
)
from slopgate.context import HookContext
from slopgate.models import EngineResult

from ._retry import attempt_fingerprint

TRACE_SCHEMA_VERSION: Final = 2
RULE_RESPONSE_VERSION: Final = "1"
_OPERATION_ID_KEYS: Final = (
    "operation_id",
    "tool_call_id",
    "toolCallId",
    "tool_use_id",
    "toolUseId",
    "call_id",
    "callId",
)
_POST_TOOL_FAILURE: Final = "PostToolUseFailure"


@dataclass(frozen=True, slots=True)
class TraceIdentity:
    """Stable identity and correlation evidence for one evaluation."""

    evaluation_id: str
    operation_id: str | None
    correlation_confidence: str


def _first_string(payload: Mapping[str, object], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _extract_operation_id(payload: Mapping[str, object]) -> str | None:
    direct = _first_string(payload, _OPERATION_ID_KEYS)
    if direct is not None:
        return direct
    for container_key in ("data", "properties", "params", "info"):
        nested = object_dict(payload.get(container_key))
        nested_id = _first_string(nested, _OPERATION_ID_KEYS)
        if nested_id is not None:
            return nested_id
    return None


def trace_identity(ctx: HookContext, repo_root: str | None) -> TraceIdentity:
    """Create one evaluation identity with explicit correlation confidence."""
    operation_id = _extract_operation_id(ctx.payload.payload)
    if operation_id is not None:
        confidence = "exact"
    elif ctx.session_id and (ctx.candidate_paths or repo_root is not None):
        confidence = "inferred"
    else:
        confidence = "unavailable"
    return TraceIdentity(
        evaluation_id=str(uuid4()),
        operation_id=operation_id,
        correlation_confidence=confidence,
    )


def _status_from_mapping(value: object) -> str | None:
    mapping = object_dict(value)
    is_error = bool_value(mapping.get("is_error"))
    if is_error is None:
        is_error = bool_value(mapping.get("isError"))
    if is_error is not None:
        return "failure" if is_error else "success"
    success = bool_value(mapping.get("success"))
    if success is not None:
        return "success" if success else "failure"
    exit_code = mapping.get("exit_code", mapping.get("exitCode"))
    if isinstance(exit_code, int) and not isinstance(exit_code, bool):
        return "success" if exit_code == 0 else "failure"
    return None


def _classify_tool_result(ctx: HookContext) -> str:
    payload = ctx.payload.payload
    explicit = payload.get("tool_outcome")
    if explicit in {"success", "failure", "unknown"}:
        return str(explicit)
    if ctx.event_name == _POST_TOOL_FAILURE:
        return "failure"
    for key in ("tool_result", "tool_response", "tool_output"):
        status = _status_from_mapping(payload.get(key))
        if status is not None:
            return status
    return "unknown"


def _classify_result(ctx: HookContext, result: EngineResult, tool_outcome: str) -> str:
    if result.errors:
        return "evaluation_error"
    if tool_outcome == "failure":
        return "tool_failed"
    decisions = {finding.decision for finding in result.findings}
    if DENY in decisions or BLOCK in decisions:
        if ctx.event_name in {PRE_TOOL_USE, PERMISSION_REQUEST}:
            return "blocked_pre_tool"
        if ctx.event_name in {POST_TOOL_USE, _POST_TOOL_FAILURE}:
            return "blocked_post_tool"
        return "unknown"
    if ASK in decisions:
        return "asked"
    return "passed_with_advisory" if result.findings else "passed_clean"


def _interventions(ctx: HookContext, result: EngineResult) -> tuple[list[str], str]:
    tags: set[str] = set()
    repair_state = "observed" if ctx.state.has_repair_plan(ctx.session_id) else "none"
    for finding in result.findings:
        if finding.rule_id == "RETRY-BUDGET-001":
            tags.update({"retry-budget", "repair-plan-requested"})
            if repair_state == "none":
                repair_state = "requested"
        repeat_count = finding.metadata.get("repeat_count")
        if isinstance(repeat_count, int) and repeat_count >= 2:
            tags.add("retry-budget")
        if any(
            key in finding.metadata
            for key in ("recommended_skill", "skill_name", "skill")
        ):
            tags.add("skill-guidance-emitted")
    if repair_state == "observed":
        tags.add("repair-plan-observed")
    return sorted(tags), repair_state


def start_trace_fields(ctx: HookContext, identity: TraceIdentity) -> ObjectDict:
    """Return correlation fields shared by start and completed result rows."""
    return {
        "trace_schema_version": TRACE_SCHEMA_VERSION,
        "evaluation_id": identity.evaluation_id,
        "operation_id": identity.operation_id,
        "correlation_confidence": identity.correlation_confidence,
        "candidate_paths": ctx.candidate_paths,
        "attempt_fingerprint": attempt_fingerprint(ctx),
    }


def completed_trace_fields(
    ctx: HookContext,
    result: EngineResult,
    identity: TraceIdentity,
) -> ObjectDict:
    """Return outcome-capable fields for one completed result record."""
    tool_outcome = _classify_tool_result(ctx)
    intervention_tags, repair_plan_state = _interventions(ctx, result)
    return {
        **start_trace_fields(ctx, identity),
        "event_outcome": _classify_result(ctx, result, tool_outcome),
        "tool_outcome": tool_outcome,
        "rule_response_version": RULE_RESPONSE_VERSION,
        "intervention_tags": intervention_tags,
        "repair_plan_state": repair_plan_state,
    }
