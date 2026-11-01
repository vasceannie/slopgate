from __future__ import annotations

from pathlib import Path
from time import monotonic

from slopgate._types import ObjectDict, ObjectMapping, object_dict_list, object_list
from slopgate.constants import (
    BLOCK,
    DENY,
    METADATA_FUNCTION,
    METADATA_PATH,
    PLATFORM_CLAUDE,
    PLATFORM_OPENCODE,
    RULE_ID_KEY,
    UNKNOWN_VALUE,
    WORKTREE_KEY,
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
from slopgate.state import RepairRequiredPayload, RepairTarget
from slopgate.util.metadata_paths import effective_metadata_path

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


def _finding_string(finding: RuleFinding, key: str) -> str | None:
    value = finding.metadata.get(key)
    return value.strip() if isinstance(value, str) and value.strip() else None


def _repair_root(ctx: HookContext) -> Path:
    return Path(ctx.state.scope) if ctx.state.scope else ctx.cwd.resolve(strict=False)


def _repair_target(ctx: HookContext, finding: RuleFinding) -> RepairTarget:
    raw_path = effective_metadata_path(finding.metadata)
    function = _finding_string(finding, METADATA_FUNCTION)
    if raw_path is None:
        return RepairTarget(
            finding.rule_id, None, None, function, "finding has no file target"
        )
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = ctx.cwd / candidate
    try:
        resolved = candidate.resolve(strict=False)
        root = _repair_root(ctx)
    except OSError:
        return RepairTarget(
            finding.rule_id, None, raw_path, function, "finding path cannot be resolved"
        )
    if not resolved.is_relative_to(root):
        return RepairTarget(
            finding.rule_id,
            None,
            raw_path,
            function,
            "finding path is outside repository root",
        )
    if not resolved.is_file():
        # Keep the in-root candidate so `slopgate repair verify` can re-resolve
        # it once the file exists; the error only explains the record-time state.
        return RepairTarget(
            finding.rule_id,
            str(resolved),
            raw_path,
            function,
            "finding path is not an existing file",
        )
    return RepairTarget(finding.rule_id, str(resolved), raw_path, function, None)


def _mark_opencode_repair_required(
    ctx: HookContext,
    quality_findings: list[RuleFinding],
) -> None:
    targets = [_repair_target(ctx, finding) for finding in quality_findings]
    call_id = str(ctx.payload.payload.get("call_id", ""))
    generation = ctx.state.repair_generation(
        targets=targets,
        event_identity=f"{ctx.session_id}\n{call_id}",
    )
    ctx.state.mark_repair_required(
        generation,
        RepairRequiredPayload(
            session_id=ctx.session_id,
            call_id=call_id,
            worktree=ctx.state.scope,
            targets=targets,
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


def _opencode_tool_name_for_policy(ctx: HookContext) -> str:
    raw_tool_name = ctx.payload.payload.get("opencode_raw_tool_name")
    if isinstance(raw_tool_name, str):
        return raw_tool_name
    native_tool_name = ctx.payload.payload.get("opencode_native_tool_name")
    return native_tool_name if isinstance(native_tool_name, str) else ctx.tool_name


def _repair_state_strings(value: object) -> list[str]:
    return [item for item in object_list(value) if isinstance(item, str) and item]


def _first_causal_label(targets: list[ObjectDict]) -> str:
    target = targets[0] if targets else {}
    rule_value = target.get(RULE_ID_KEY)
    path_value = target.get(METADATA_PATH)
    rule = rule_value if isinstance(rule_value, str) and rule_value else None
    path = path_value if isinstance(path_value, str) and path_value else None
    if rule and path:
        return f"{rule} in {path}"
    if rule:
        return f"rule {rule}"
    if path:
        return f"file {path}"
    return "invalid or legacy repair state"


def _opencode_repair_recovery_message(
    generation_label: str,
    causal_label: str,
) -> str:
    return (
        "STOP: do not retry this blocked mutation; equivalent retries remain blocked "
        f"until generation {generation_label} clears. Recovery protocol: "
        f"(1) read the first causal finding: {causal_label}; "
        "(2) inspect affected files with declared read-only tools; "
        "(3) make one focused repair with an allowed mutation tool "
        "(write, edit, patch); "
        "(4) run slopgate_verify_repair; it resolves the pending generation from repair "
        "state and clears it only after clean verification. Allowed during repair: "
        "declared read-only tools, write/edit/patch, slopgate_verify_repair, Code Mode "
        "execute (each tool it calls is gated and its fetch is denied), exact slopgate "
        "lint check; compound shell, diagnostic, and wrapper-tool retries remain blocked."
    )


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
    required = ctx.state.get_repair_required()
    if required is None or opencode_tool_allowed_during_repair(
        _opencode_tool_name_for_policy(ctx), ctx.tool_input
    ):
        return None
    generation = required.get("generation")
    generation_label = generation if isinstance(generation, str) else UNKNOWN_VALUE
    worktree = required.get(WORKTREE_KEY)
    worktree_label = worktree if isinstance(worktree, str) else UNKNOWN_VALUE
    targets = object_dict_list(required.get("targets"))
    rule_ids = _repair_state_strings(required.get("rule_ids"))
    paths = _repair_state_strings(required.get("paths"))
    return RuleFinding(
        rule_id="OC-REPAIR-001",
        title="OpenCode repair required",
        severity=Severity.CRITICAL,
        decision=DENY,
        message=_opencode_repair_recovery_message(
            generation_label,
            _first_causal_label(targets),
        ),
        metadata={
            "generation": generation_label,
            "rule_ids": rule_ids,
            "paths": paths,
            "targets": targets,
            WORKTREE_KEY: worktree_label,
        },
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
    if ctx.payload.payload.get("opencode_hook_event") == "tool.execute.before":
        unresolved = unresolved_opencode_projection_finding(
            _opencode_tool_name_for_policy(ctx), ctx.tool_input, ctx.event_name
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
