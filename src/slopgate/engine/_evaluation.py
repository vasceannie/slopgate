from __future__ import annotations

from time import monotonic

from slopgate._types import ObjectDict, ObjectMapping
from slopgate.constants import (
    PLATFORM_OPENCODE,
    PLATFORM_CLAUDE,
    UNKNOWN_VALUE,
    BLOCK,
    DENY,
)
from slopgate.adapters import get_adapter
from slopgate.adapters.opencode_projection import unresolved_opencode_projection_finding
from slopgate.context import HookContext, build_context
from slopgate.lint._helpers import (
    reset_request_analysis_cache,
    reset_request_timing,
)
from slopgate.models import EngineResult, RuleFinding, Severity
from slopgate.opencode_tool_capabilities import opencode_tool_allowed_during_repair
from slopgate.state import RepairRequiredPayload

from .advisories import compact_context_advisories
from ._render import render_output
from ._retry import (
    apply_loop_aware_steering,
    capture_repair_plan_signal,
    dedupe_findings,
    enforce_retry_budget,
    filter_search_reminder_dedupe,
    inject_recent_failure_context,
)
from ._runner import EnforcementMode, run_rules
from ._trace_payloads import (
    evaluation_metadata,
    payload_for_done,
    subprocess_startup_ms,
    write_start_trace,
)


def _is_opencode_post_tool(
    ctx: HookContext,
    platform: str,
    mode: EnforcementMode,
) -> bool:
    return (
        platform == PLATFORM_OPENCODE
        and mode == "repo_strict"
        and ctx.event_name == "PostToolUse"
    )


def _execution_failed(ctx: HookContext) -> bool:
    outcome = str(ctx.payload.payload.get("execution_outcome", ""))
    return outcome.strip().lower() in {"failed", "cancelled"}


def _blocking_findings(findings: list[RuleFinding]) -> list[RuleFinding]:
    return [finding for finding in findings if finding.decision in {DENY, BLOCK}]


def _clear_opencode_repair_required(ctx: HookContext) -> None:
    if not ctx.mutating:
        return
    required = ctx.state.get_repair_required()
    generation = required.get("generation") if required else None
    if isinstance(generation, str) and generation:
        ctx.state.clear_repair_required(generation)


def _mark_opencode_repair_required(
    ctx: HookContext,
    quality_findings: list[RuleFinding],
) -> None:
    rule_ids = [finding.rule_id for finding in quality_findings]
    paths = list(ctx.candidate_paths)
    call_id = str(ctx.payload.payload.get("call_id", ""))
    generation = ctx.state.repair_generation(
        rule_ids=rule_ids,
        paths=paths,
        event_identity=f"{ctx.session_id}\n{call_id}",
    )
    ctx.state.mark_repair_required(
        generation,
        RepairRequiredPayload(
            session_id=ctx.session_id,
            call_id=call_id,
            rule_ids=rule_ids,
            paths=paths,
        ),
    )


def _record_opencode_repair_required(
    ctx: HookContext,
    findings: list[RuleFinding],
    platform: str,
    mode: EnforcementMode = "repo_strict",
) -> None:
    if not _is_opencode_post_tool(ctx, platform, mode) or _execution_failed(ctx):
        return
    quality_findings = _blocking_findings(findings)
    if quality_findings:
        _mark_opencode_repair_required(ctx, quality_findings)
        return
    _clear_opencode_repair_required(ctx)


def _opencode_repair_required_finding(
    ctx: HookContext,
    platform: str,
    mode: EnforcementMode = "repo_strict",
) -> RuleFinding | None:
    """Return the Python-path repair gate finding for OpenCode pre-tool calls."""
    if (
        platform != PLATFORM_OPENCODE
        or mode != "repo_strict"
        or ctx.event_name != "PreToolUse"
    ):
        return None
    native_tool_name = ctx.payload.payload.get("opencode_native_tool_name")
    repair_tool_name = (
        native_tool_name if isinstance(native_tool_name, str) else ctx.tool_name
    )
    required = ctx.state.get_repair_required()
    if required is None or opencode_tool_allowed_during_repair(
        repair_tool_name, ctx.tool_input
    ):
        return None
    generation = required.get("generation")
    generation_label = generation if isinstance(generation, str) else UNKNOWN_VALUE
    return RuleFinding(
        rule_id="OC-REPAIR-001",
        title="OpenCode repair required",
        severity=Severity.CRITICAL,
        decision=DENY,
        message=(
            f"Repair required for generation {generation_label}; use declared read-only "
            "tools, write/edit/apply_patch, the repair verifier, or exact lint check."
        ),
        metadata={"generation": generation_label},
    )


def _inject_opencode_gate_findings(
    ctx: HookContext,
    findings: list[RuleFinding],
    platform: str,
    mode: EnforcementMode = "repo_strict",
) -> None:
    if platform != PLATFORM_OPENCODE or mode != "repo_strict":
        return
    repair_required = _opencode_repair_required_finding(ctx, platform, mode)
    if repair_required is not None:
        findings.append(repair_required)
    unresolved = unresolved_opencode_projection_finding(
        ctx.tool_name, ctx.tool_input, ctx.event_name
    )
    if unresolved is not None:
        findings.append(unresolved)


def _evaluate_payload_inner(
    payload_dict: ObjectMapping,
    platform: str,
    startup_ms: float,
    evaluation_start: float,
) -> EngineResult:
    trace_platform = platform.strip().lower() or UNKNOWN_VALUE
    adapter_platform = (
        PLATFORM_CLAUDE if trace_platform == UNKNOWN_VALUE else trace_platform
    )
    normalization_context_start = monotonic()
    adapter = get_adapter(adapter_platform)
    ctx = build_context(adapter.normalize_payload(payload_dict))
    metadata = evaluation_metadata(ctx, trace_platform)
    normalization_context_ms = int((monotonic() - normalization_context_start) * 1000)
    trace_event_ms = write_start_trace(ctx, metadata)

    capture_repair_plan_signal(ctx)
    rule_engine_start = monotonic()
    acc = run_rules(ctx, trace_platform, metadata.enforcement_mode)
    rule_engine_ms = int((monotonic() - rule_engine_start) * 1000)
    enforce_retry_budget(ctx, acc.findings)
    apply_loop_aware_steering(ctx, acc.findings)
    inject_recent_failure_context(ctx, acc.findings)
    acc.findings = filter_search_reminder_dedupe(ctx, acc.findings)
    acc.findings = dedupe_findings(acc.findings)
    _inject_opencode_gate_findings(
        ctx, acc.findings, trace_platform, metadata.enforcement_mode
    )
    _record_opencode_repair_required(
        ctx, acc.findings, trace_platform, metadata.enforcement_mode
    )
    compact_context_advisories(ctx, acc.findings)
    render_start = monotonic()
    output = render_output(ctx, acc.findings, adapter=adapter)
    render_ms = int((monotonic() - render_start) * 1000)

    result = EngineResult(ctx.event_name, acc.findings, output, acc.errors)
    timing: ObjectDict = {
        "collector_ms": reset_request_timing(),
        "evaluation_ms": int((monotonic() - evaluation_start) * 1000),
        "normalization_context_ms": normalization_context_ms,
        "render_ms": render_ms,
        "rule_engine_ms": rule_engine_ms,
        "subprocess_startup_ms": startup_ms,
        "trace_event_ms": trace_event_ms,
    }
    ctx.trace.result(payload_for_done(ctx, metadata, result, timing))
    return result


def evaluate_payload(
    payload_dict: ObjectMapping,
    platform: str = UNKNOWN_VALUE,
) -> EngineResult:
    reset_request_analysis_cache()
    reset_request_timing()
    startup_ms = subprocess_startup_ms(payload_dict)
    evaluation_start = monotonic()
    try:
        return _evaluate_payload_inner(
            payload_dict, platform, startup_ms, evaluation_start
        )
    finally:
        reset_request_analysis_cache()
        reset_request_timing()
