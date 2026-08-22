"""Trace payload construction and phase timing for engine evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import monotonic, time

from slopgate._types import ObjectDict, ObjectMapping, is_object_dict, object_dict
from slopgate.config import resolve_repo_root
from slopgate.constants import (
    MILLISECONDS_PER_SECOND,
    PLATFORM_KEY,
    SESSION_ID,
    TOOL_EDIT,
    TOOL_GLOB,
    TOOL_GREP,
    TOOL_READ,
    TOOL_WEB_FETCH,
    TOOL_WEB_SEARCH,
    TOOL_WRITE,
)
from slopgate.context import HookContext
from slopgate.models import EngineResult

from ._fingerprints import (
    effective_policy_fingerprint,
    guidance_fingerprint,
    slopgate_version,
)
from ._render import serialize_findings
from ._runner import EnforcementMode, platform_capability, resolve_enforcement_mode


@dataclass(frozen=True, slots=True)
class EvaluationMetadata:
    platform: str
    platform_source: str
    enforcement_mode: EnforcementMode
    resolved_repo_root: Path | None
    platform_capability: str
    degraded_reason: str | None

    @property
    def repo_root_text(self) -> str | None:
        return str(self.resolved_repo_root) if self.resolved_repo_root else None


def evaluation_metadata(ctx: HookContext, platform: str) -> EvaluationMetadata:
    capability, degraded_reason = platform_capability(platform)
    return EvaluationMetadata(
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
_TRACE_OPTIONAL_FIELDS = (
    "opencode_session_id",
    "call_id",
    "session_identity_source",
    "session_title",
    "session_title_source",
    "execution_outcome",
    "mutation_outcome",
    "evidence_tier",
    "tool_title",
    "tool_metadata",
)


def _extract_model_provider(payload: ObjectMapping) -> tuple[str | None, str | None]:
    model = payload.get("model") or payload.get("model_name")
    provider = (
        payload.get("provider")
        or payload.get("model_provider")
        or payload.get("modelProvider")
    )
    return (str(model) if model else None, str(provider) if provider else None)


def _fallback_command(tool_name: str, tool_input: ObjectDict) -> str | None:
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
    return str(cmd) if cmd else _fallback_command(ctx.tool_name, tool_input)


def _extract_tool_output(payload: ObjectMapping) -> str | None:
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


def _trace_optional_fields(payload: ObjectMapping) -> ObjectDict:
    fields = {key: payload[key] for key in _TRACE_OPTIONAL_FIELDS if key in payload}
    if "tool_output" in payload:
        fields["tool_output_raw"] = payload["tool_output"]
    return fields


def _trace_drilldown_fields(ctx: HookContext) -> ObjectDict:
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
        **_trace_optional_fields(ctx.payload.payload),
    }


def _payload_for_start(ctx: HookContext, metadata: EvaluationMetadata) -> ObjectDict:
    return {
        PLATFORM_KEY: metadata.platform,
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


def write_start_trace(ctx: HookContext, metadata: EvaluationMetadata) -> int:
    """Write the start row and return its trace latency in milliseconds."""
    started = monotonic()
    ctx.trace.event(_payload_for_start(ctx, metadata))
    return int((monotonic() - started) * MILLISECONDS_PER_SECOND)


def subprocess_startup_ms(payload: ObjectMapping) -> int:
    started_at_ms = payload.get("slopgate_subprocess_started_at_ms")
    if not isinstance(started_at_ms, int | float):
        return 0
    elapsed_ms = time() * MILLISECONDS_PER_SECOND - started_at_ms
    return max(0, int(elapsed_ms))


def payload_for_done(
    ctx: HookContext,
    metadata: EvaluationMetadata,
    result: EngineResult,
    timing: ObjectDict,
) -> ObjectDict:
    return {
        PLATFORM_KEY: metadata.platform,
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
        "candidate_paths": ctx.candidate_paths,
        "languages": sorted(ctx.languages),
        "slopgate_version": slopgate_version(),
        "effective_policy_fingerprint": effective_policy_fingerprint(ctx.config),
        "guidance_fingerprint": guidance_fingerprint(ctx.config),
        "enforcement_mode": metadata.enforcement_mode,
        "resolved_repo_root": metadata.repo_root_text,
        **_trace_drilldown_fields(ctx),
    }
