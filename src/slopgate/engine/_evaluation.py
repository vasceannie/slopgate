from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from vibeforcer._types import ObjectDict
from vibeforcer.adapters import get_adapter
from vibeforcer.config import resolve_repo_root
from vibeforcer.context import HookContext, build_context
from vibeforcer.models import EngineResult

from ._render import _serialize_findings, render_output
from ._retry import (
    _apply_loop_aware_steering,
    _capture_repair_plan_signal,
    _dedupe_findings,
    _enforce_retry_budget,
    _filter_search_reminder_dedupe,
    _inject_recent_failure_context,
)
from ._runner import (
    EnforcementMode,
    _EvalAccumulator,
    _platform_capability,
    _resolve_enforcement_mode,
    _run_rules,
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
    capability, degraded_reason = _platform_capability(platform)
    return _EvaluationMetadata(
        platform=platform,
        enforcement_mode=_resolve_enforcement_mode(ctx),
        resolved_repo_root=resolve_repo_root(Path(ctx.cwd) if ctx.cwd else Path.cwd()),
        platform_capability=capability,
        degraded_reason=degraded_reason,
    )


def _trace_evaluation_start(ctx: HookContext, metadata: _EvaluationMetadata) -> None:
    ctx.trace.event(
        {
            "platform": metadata.platform,
            "platform_capability": metadata.platform_capability,
            "degraded_reason": metadata.degraded_reason,
            "event_name": ctx.event_name,
            "session_id": ctx.session_id,
            "tool_name": ctx.tool_name,
            "candidate_paths": ctx.candidate_paths,
            "languages": sorted(ctx.languages),
            "enforcement_mode": metadata.enforcement_mode,
            "resolved_repo_root": metadata.repo_root_text,
        }
    )


def _trace_evaluation_result(
    ctx: HookContext,
    metadata: _EvaluationMetadata,
    acc: _EvalAccumulator,
    output: ObjectDict | None,
) -> None:
    ctx.trace.result(
        {
            "platform": metadata.platform,
            "platform_capability": metadata.platform_capability,
            "degraded_reason": metadata.degraded_reason,
            "event_name": ctx.event_name,
            "session_id": ctx.session_id,
            "tool_name": ctx.tool_name,
            "findings": _serialize_findings(acc.findings),
            "errors": acc.errors,
            "output": output,
            "enforcement_mode": metadata.enforcement_mode,
            "resolved_repo_root": metadata.repo_root_text,
        }
    )


def evaluate_payload(
    payload_dict: Mapping[str, object],
    platform: str = "claude",
) -> EngineResult:
    adapter = get_adapter(platform)
    ctx = build_context(adapter.normalize_payload(payload_dict))
    metadata = _evaluation_metadata(ctx, platform)
    _trace_evaluation_start(ctx, metadata)

    _capture_repair_plan_signal(ctx)
    acc = _run_rules(ctx, platform, metadata.enforcement_mode)
    _enforce_retry_budget(ctx, acc.findings)
    _apply_loop_aware_steering(ctx, acc.findings)
    _inject_recent_failure_context(ctx, acc.findings)
    acc.findings = _filter_search_reminder_dedupe(ctx, acc.findings)
    acc.findings = _dedupe_findings(acc.findings)
    output = render_output(ctx, acc.findings, adapter=adapter)

    _trace_evaluation_result(ctx, metadata, acc, output)
    return EngineResult(
        event_name=ctx.event_name,
        findings=acc.findings,
        output=output,
        errors=acc.errors,
    )
