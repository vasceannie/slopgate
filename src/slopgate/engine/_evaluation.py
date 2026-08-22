from __future__ import annotations

from collections.abc import Mapping
from time import monotonic

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
from slopgate.models import EngineResult, RuleFinding
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
from ._runner import run_rules
from ._trace_payloads import (
    evaluation_metadata,
    payload_for_done,
    subprocess_startup_ms,
    write_start_trace,
)


def _record_opencode_repair_required(
    ctx: HookContext, findings: list[RuleFinding], platform: str
) -> None:
    if platform != PLATFORM_OPENCODE:
        return
    if ctx.event_name not in {"PostToolUse", "PostToolUseFailure"}:
        return
    quality_findings = [
        finding
        for finding in findings
        if finding.decision in {DENY, BLOCK}
    ]
    if not quality_findings:
        return
    rule_ids = [finding.rule_id for finding in quality_findings]
    paths = [target.path for target in ctx.content_targets]
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


def evaluate_payload(
    payload_dict: Mapping[str, object],
    platform: str = UNKNOWN_VALUE,
) -> EngineResult:
    reset_request_analysis_cache()
    reset_request_timing()
    startup_ms = subprocess_startup_ms(payload_dict)
    evaluation_start = monotonic()
    try:
        trace_platform = platform.strip().lower() or UNKNOWN_VALUE
        adapter_platform = PLATFORM_CLAUDE if trace_platform == UNKNOWN_VALUE else trace_platform
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
        if trace_platform == PLATFORM_OPENCODE:
            unresolved = unresolved_opencode_projection_finding(
                ctx.tool_name, ctx.tool_input, ctx.event_name
            )
            if unresolved is not None:
                acc.findings.append(unresolved)
        _record_opencode_repair_required(ctx, acc.findings, trace_platform)
        compact_context_advisories(ctx, acc.findings)
        render_start = monotonic()
        output = render_output(ctx, acc.findings, adapter=adapter)
        render_ms = int((monotonic() - render_start) * 1000)

        result = EngineResult(ctx.event_name, acc.findings, output, acc.errors)
        timing: dict[str, object] = {
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
    finally:
        reset_request_analysis_cache()
        reset_request_timing()
