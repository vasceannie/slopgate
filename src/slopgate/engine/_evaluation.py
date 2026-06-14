from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from time import monotonic

from slopgate.constants import (
    SESSION_ID,
    PLATFORM_CLAUDE,
    TOOL_WRITE,
    TOOL_EDIT,
    TOOL_READ,
    TOOL_GLOB,
    TOOL_GREP,
    TOOL_WEB_SEARCH,
    TOOL_WEB_FETCH,
    UNKNOWN_VALUE,
)
from slopgate.adapters import PlatformAdapter, get_adapter
from slopgate.config import resolve_repo_root
from slopgate.context import HookContext, build_context
from slopgate.lint._helpers import reset_request_analysis_cache
from slopgate.models import EngineResult

from .._types import is_object_dict, object_dict
from ._render import serialize_findings, render_output
from ._retry import (
    apply_loop_aware_steering,
    capture_repair_plan_signal,
    dedupe_findings,
    enforce_retry_budget,
    filter_search_reminder_dedupe,
    inject_recent_failure_context,
)
from ._runner import (
    EnforcementMode,
    platform_capability,
    resolve_enforcement_mode,
    run_rules,
)


@dataclass(frozen=True, slots=True)
class _EvaluationMetadata:
    platform: str
    platform_source: str
    enforcement_mode: EnforcementMode
    resolved_repo_root: Path | None
    platform_capability: str
    degraded_reason: str | None

    @property
    def repo_root_text(self) -> str | None:
        return str(self.resolved_repo_root) if self.resolved_repo_root else None


@dataclass(frozen=True, slots=True)
class _EvaluationTraceContext:
    ctx: HookContext
    metadata: _EvaluationMetadata
    started_at: float


def _evaluation_metadata(ctx: HookContext, platform: str) -> _EvaluationMetadata:
    capability, degraded_reason = platform_capability(platform)
    return _EvaluationMetadata(
        platform=platform,
        platform_source=platform,
        enforcement_mode=resolve_enforcement_mode(ctx),
        resolved_repo_root=resolve_repo_root(Path(ctx.cwd)),
        platform_capability=capability,
        degraded_reason=degraded_reason,
    )


_FILE_TOOLS = (TOOL_WRITE, TOOL_EDIT, TOOL_READ)
_SEARCH_TOOLS = (TOOL_GLOB, TOOL_GREP)
_WEB_TOOLS = (TOOL_WEB_SEARCH, TOOL_WEB_FETCH)


def _extract_model_provider(
    payload: Mapping[str, object],
) -> tuple[str | None, str | None]:
    model = payload.get("model") or payload.get("model_name")
    provider = (
        payload.get("provider")
        or payload.get("model_provider")
        or payload.get("modelProvider")
    )
    return (str(model) if model else None, str(provider) if provider else None)


def _fallback_command(tool_name: str, tool_input: dict[str, object]) -> str | None:
    if tool_name in _FILE_TOOLS:
        path = (
            tool_input.get("filePath")
            or tool_input.get("file_path")
            or tool_input.get("path")
        )
        return f"{tool_name.lower()} {path}" if path else None
    if tool_name in _SEARCH_TOOLS:
        pattern = tool_input.get("pattern")
        return f"{tool_name.lower()} {pattern}" if pattern else None
    if tool_name in _WEB_TOOLS:
        url = tool_input.get("url") or tool_input.get("query")
        return f"{tool_name.lower()} {url}" if url else None
    return None


def _extract_command(ctx: HookContext) -> str | None:
    command = ctx.payload.shell_command
    if command:
        return command
    tool_input = ctx.payload.tool_input
    if not tool_input:
        return None
    cmd = tool_input.get("command") or tool_input.get("script") or tool_input.get("cmd")
    if cmd:
        return str(cmd)
    return _fallback_command(ctx.tool_name, tool_input)


def _extract_tool_output(payload: Mapping[str, object]) -> str | None:
    tool_output = (
        payload.get("tool_result")
        or payload.get("tool_response")
        or payload.get("tool_output")
    )
    if tool_output is None:
        return None
    if is_object_dict(tool_output):
        output_data = object_dict(tool_output)
        stdout = output_data.get("stdout")
        stderr = output_data.get("stderr")
        if stdout or stderr:
            parts: list[str] = [f"stdout:\n{stdout or ''}"]
            if stderr:
                parts.append(f"stderr:\n{stderr}")
            return "\n".join(parts)
        return str(tool_output)
    return str(tool_output)


def _trace_drilldown_fields(ctx: HookContext) -> dict[str, object]:
    model, provider = _extract_model_provider(ctx.payload.payload)
    return {
        "model": model,
        "provider": provider,
        "command": _extract_command(ctx),
        "tool_output": _extract_tool_output(ctx.payload.payload),
        "tool_input": ctx.tool_input,
        "tool_intent": ctx.tool_intent,
        "intent_reason": ctx.intent_reason,
        "read_only": ctx.read_only,
        "mutating": ctx.mutating,
        "candidate_path_source": ctx.candidate_path_source,
        "platform_event_name": ctx.platform_event_name,
    }


def _payload_for_start(
    ctx: HookContext, metadata: _EvaluationMetadata
) -> dict[str, object]:
    return {
        "platform": metadata.platform,
        "platform_source": metadata.platform_source,
        "platform_capability": metadata.platform_capability,
        "degraded_reason": metadata.degraded_reason,
        "event_name": ctx.event_name,
        SESSION_ID: ctx.session_id,
        "tool_name": ctx.tool_name,
        "candidate_paths": ctx.candidate_paths,
        "languages": sorted(ctx.languages),
        "enforcement_mode": metadata.enforcement_mode,
        "resolved_repo_root": metadata.repo_root_text,
        **_trace_drilldown_fields(ctx),
    }


def _payload_for_done(
    ctx: HookContext,
    metadata: _EvaluationMetadata,
    result: EngineResult,
    timing: dict[str, object],
) -> dict[str, object]:
    return {
        "platform": metadata.platform,
        "platform_source": metadata.platform_source,
        "platform_capability": metadata.platform_capability,
        "degraded_reason": metadata.degraded_reason,
        "event_name": ctx.event_name,
        SESSION_ID: ctx.session_id,
        "tool_name": ctx.tool_name,
        "findings": serialize_findings(result.findings),
        "errors": result.errors,
        "output": result.output,
        "timing": timing,
        "enforcement_mode": metadata.enforcement_mode,
        "resolved_repo_root": metadata.repo_root_text,
        **_trace_drilldown_fields(ctx),
    }


def _trace_evaluation_failure(
    trace_context: _EvaluationTraceContext, exc: Exception
) -> None:
    timing: dict[str, object] = {
        "evaluation_ms": int((monotonic() - trace_context.started_at) * 1000)
    }
    result = EngineResult(
        event_name=trace_context.ctx.event_name,
        errors=[f"{exc.__class__.__name__}: {exc}"],
    )
    trace_context.ctx.trace.result(
        _payload_for_done(trace_context.ctx, trace_context.metadata, result, timing)
    )


def _evaluate_rules(
    ctx: HookContext,
    trace_platform: str,
    metadata: _EvaluationMetadata,
    adapter: PlatformAdapter,
) -> tuple[EngineResult, int]:
    capture_repair_plan_signal(ctx)
    rule_engine_start = monotonic()
    acc = run_rules(ctx, trace_platform, metadata.enforcement_mode)
    rule_engine_ms = int((monotonic() - rule_engine_start) * 1000)
    enforce_retry_budget(ctx, acc.findings)
    apply_loop_aware_steering(ctx, acc.findings)
    inject_recent_failure_context(ctx, acc.findings)
    acc.findings = filter_search_reminder_dedupe(ctx, acc.findings)
    acc.findings = dedupe_findings(acc.findings)
    output = render_output(ctx, acc.findings, adapter=adapter)
    result = EngineResult(
        event_name=ctx.event_name,
        findings=acc.findings,
        output=output,
        errors=acc.errors,
    )
    return result, rule_engine_ms


def evaluate_payload(
    payload_dict: Mapping[str, object],
    platform: str = UNKNOWN_VALUE,
) -> EngineResult:
    reset_request_analysis_cache()
    evaluation_start = monotonic()
    ctx: HookContext | None = None
    trace_context: _EvaluationTraceContext | None = None
    try:
        trace_platform = platform.strip().lower() or UNKNOWN_VALUE
        adapter_platform = (
            PLATFORM_CLAUDE if trace_platform == UNKNOWN_VALUE else trace_platform
        )
        adapter = get_adapter(adapter_platform)
        ctx = build_context(
            adapter.normalize_payload(payload_dict), buffered_trace=True
        )
        metadata = _evaluation_metadata(ctx, trace_platform)
        trace_context = _EvaluationTraceContext(ctx, metadata, evaluation_start)
        ctx.trace.event(_payload_for_start(ctx, metadata))

        result, rule_engine_ms = _evaluate_rules(ctx, trace_platform, metadata, adapter)
        timing: dict[str, object] = {
            "evaluation_ms": int((monotonic() - trace_context.started_at) * 1000),
            "rule_engine_ms": rule_engine_ms,
        }
        ctx.trace.result(_payload_for_done(ctx, metadata, result, timing))
        return result
    except Exception as exc:
        if trace_context is not None:
            _trace_evaluation_failure(trace_context, exc)
        raise
    finally:
        if ctx is not None:
            ctx.trace.flush()
        reset_request_analysis_cache()
