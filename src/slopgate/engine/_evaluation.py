from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from slopgate.constants import (
    SESSION_ID,
    TOOL_WRITE,
    TOOL_EDIT,
    TOOL_READ,
    TOOL_GLOB,
    TOOL_GREP,
    TOOL_WEB_SEARCH,
    TOOL_WEB_FETCH,
)
from slopgate.adapters import get_adapter
from slopgate.config import resolve_repo_root
from slopgate.context import HookContext, build_context
from slopgate.models import EngineResult

from .._types import is_object_dict
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
    enforcement_mode: EnforcementMode
    resolved_repo_root: Path | None
    platform_capability: str
    degraded_reason: str | None

    @property
    def repo_root_text(self) -> str | None:
        return str(self.resolved_repo_root) if self.resolved_repo_root else None


def _evaluation_metadata(ctx: HookContext, platform: str) -> _EvaluationMetadata:
    capability, degraded_reason = platform_capability(platform)
    return _EvaluationMetadata(
        platform=platform,
        enforcement_mode=resolve_enforcement_mode(ctx),
        resolved_repo_root=resolve_repo_root(Path(ctx.cwd) if ctx.cwd else Path.cwd()),
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
        stdout = tool_output.get("stdout")
        stderr = tool_output.get("stderr")
        if stdout or stderr:
            parts: list[str] = [f"stdout:\n{stdout or ''}"]
            if stderr:
                parts.append(f"stderr:\n{stderr}")
            return "\n".join(parts)
        return str(tool_output)
    return str(tool_output)


def _trace_drilldown_fields(
    ctx: HookContext, metadata: _EvaluationMetadata
) -> dict[str, object]:
    model, provider = _extract_model_provider(ctx.payload.payload)
    return {
        "model": model,
        "provider": provider,
        "command": _extract_command(ctx),
        "tool_output": _extract_tool_output(ctx.payload.payload),
        "tool_input": ctx.tool_input,
    }


def _payload_for_start(
    ctx: HookContext, metadata: _EvaluationMetadata
) -> dict[str, object]:
    return {
        "platform": metadata.platform,
        "platform_capability": metadata.platform_capability,
        "degraded_reason": metadata.degraded_reason,
        "event_name": ctx.event_name,
        SESSION_ID: ctx.session_id,
        "tool_name": ctx.tool_name,
        "candidate_paths": ctx.candidate_paths,
        "languages": sorted(ctx.languages),
        "enforcement_mode": metadata.enforcement_mode,
        "resolved_repo_root": metadata.repo_root_text,
        **_trace_drilldown_fields(ctx, metadata),
    }


def _payload_for_done(
    ctx: HookContext,
    metadata: _EvaluationMetadata,
    result: EngineResult,
) -> dict[str, object]:
    return {
        "platform": metadata.platform,
        "platform_capability": metadata.platform_capability,
        "degraded_reason": metadata.degraded_reason,
        "event_name": ctx.event_name,
        SESSION_ID: ctx.session_id,
        "tool_name": ctx.tool_name,
        "findings": serialize_findings(result.findings),
        "errors": result.errors,
        "output": result.output,
        "enforcement_mode": metadata.enforcement_mode,
        "resolved_repo_root": metadata.repo_root_text,
        **_trace_drilldown_fields(ctx, metadata),
    }


def evaluate_payload(
    payload_dict: Mapping[str, object],
    platform: str = "claude",
) -> EngineResult:
    adapter = get_adapter(platform)
    ctx = build_context(adapter.normalize_payload(payload_dict))
    metadata = _evaluation_metadata(ctx, platform)
    ctx.trace.event(_payload_for_start(ctx, metadata))

    capture_repair_plan_signal(ctx)
    acc = run_rules(ctx, platform, metadata.enforcement_mode)
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
    ctx.trace.result(_payload_for_done(ctx, metadata, result))
    return result
