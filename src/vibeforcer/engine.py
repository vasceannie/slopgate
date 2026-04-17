from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Mapping
from pathlib import Path
from time import monotonic

from vibeforcer._types import ObjectDict
from vibeforcer.adapters import get_adapter
from vibeforcer.adapters.base import PlatformAdapter
from typing import Literal

from vibeforcer.config import (
    is_path_skipped,
    is_repo_disabled,
    is_repo_enrolled,
    resolve_repo_root,
)
from vibeforcer.context import HookContext, build_context
from vibeforcer.enrichment import enrich_findings
from vibeforcer.models import EngineResult, RuleFinding, Severity
from vibeforcer.rules import build_always_on_rules, build_repo_strict_rules
from vibeforcer.rules.base import Rule
from vibeforcer.util import warning
from vibeforcer.util.payloads import is_edit_like_tool


DECISION_ORDER: dict[str | None, int] = {
    "deny": 4,
    "block": 4,
    "ask": 3,
    "allow": 2,
    None: 0,
}


def _finding_sort_key(item: RuleFinding) -> tuple[int, int]:
    return (DECISION_ORDER.get(item.decision, 0), int(item.severity))


def _merge_updated_input(findings: list[RuleFinding]) -> dict[str, object]:
    merged: dict[str, object] = {}
    for finding in findings:
        merged.update(finding.updated_input)
    return merged


def _collect_context(findings: list[RuleFinding]) -> str | None:
    parts = [item.additional_context for item in findings if item.additional_context]
    if not parts:
        return None
    return "\n\n".join(dict.fromkeys(parts))


def _top_decision(findings: list[RuleFinding]) -> str | None:
    if not findings:
        return None
    return max(findings, key=_finding_sort_key).decision


def _apply_severity_overrides(
    findings: list[RuleFinding],
    overrides: dict[str, str],
) -> None:
    """Mutate findings in-place to apply per-repo severity overrides."""
    for finding in findings:
        if finding.rule_id not in overrides:
            continue
        override = overrides[finding.rule_id]
        if override.lower() == "warn":
            finding.severity = Severity.LOW
            finding.decision = None
        else:
            finding.severity = Severity.from_value(override)


def _serialize_findings(findings: list[RuleFinding]) -> list[dict[str, object]]:
    return [
        {
            "rule_id": item.rule_id,
            "severity": item.severity.as_name(),
            "decision": item.decision,
            "message": item.message,
            "additional_context": item.additional_context,
            "metadata": item.metadata,
        }
        for item in findings
    ]


def _trace_identity(ctx: HookContext, platform: str) -> dict[str, object]:
    return {
        "platform": platform,
        "event_name": ctx.event_name,
        "session_id": ctx.session_id,
        "tool_name": ctx.tool_name,
    }


def _platform_capability(platform: str) -> tuple[str, str | None]:
    normalized = platform.strip().lower()
    if normalized == "opencode":
        return (
            "degraded",
            "opencode lacks full prompt/stop blocking parity and post-tool deny is advisory",
        )
    if normalized == "codex":
        return ("partial", "codex hook semantics differ from claude in some environments")
    return ("full", None)


def _error_trace_payload(
    identity: dict[str, object],
    rule_id: str,
    exc: Exception,
    elapsed_ms: float,
) -> dict[str, object]:
    """Build the trace payload dict for a rule evaluation error."""
    payload = dict(identity)
    payload.update(
        {
            "rule_id": rule_id,
            "elapsed_ms": elapsed_ms,
            "error": repr(exc),
        }
    )
    return payload


@dataclass(slots=True)
class _EvalAccumulator:
    """Groups mutable state passed through the evaluation pipeline."""

    findings: list[RuleFinding] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _trace_findings(
    ctx: HookContext,
    platform: str,
    items: list[RuleFinding],
    elapsed_ms: float,
) -> None:
    identity = _trace_identity(ctx, platform)
    for item in items:
        payload = dict(identity)
        payload.update(
            {
                "rule_id": item.rule_id,
                "elapsed_ms": elapsed_ms,
                "severity": item.severity.as_name(),
                "decision": item.decision,
                "message": item.message,
                "additional_context": item.additional_context,
                "metadata": item.metadata,
            }
        )
        ctx.trace.rule(payload)


def _run_rule(
    rule: Rule,
    ctx: HookContext,
    platform: str,
    acc: _EvalAccumulator,
) -> None:
    """Evaluate a single rule, collecting findings and errors."""
    identity = _trace_identity(ctx, platform)
    start = monotonic()
    try:
        result = rule.evaluate(ctx)
        elapsed_ms = round((monotonic() - start) * 1000.0, 3)
        if not result:
            return
        _apply_severity_overrides(result, ctx.config.severity_overrides)
        acc.findings.extend(result)
        _trace_findings(ctx, platform, result, elapsed_ms)
    except Exception as exc:
        elapsed_ms = round((monotonic() - start) * 1000.0, 3)
        acc.errors.append(f"{rule.rule_id}: {exc}")
        warning(
            "rule evaluation failed",
            rule_id=rule.rule_id,
            event_name=ctx.event_name,
            tool_name=ctx.tool_name,
            error=str(exc),
        )
        ctx.trace.rule(_error_trace_payload(identity, rule.rule_id, exc, elapsed_ms))


def _safe_enrich(
    ctx: HookContext,
    platform: str,
    acc: _EvalAccumulator,
) -> None:
    """Run enrichment with error capture instead of silent swallow."""
    identity = _trace_identity(ctx, platform)
    findings_before = len(acc.findings)
    start = monotonic()
    try:
        enrich_findings(acc.findings, ctx)
        elapsed_ms = round((monotonic() - start) * 1000.0, 3)
        findings_after = len(acc.findings)
        payload = dict(identity)
        payload.update(
            {
                "rule_id": "ENRICHMENT",
                "elapsed_ms": elapsed_ms,
                "metadata": {
                    "findings_before": findings_before,
                    "findings_after": findings_after,
                    "findings_delta": findings_after - findings_before,
                },
            }
        )
        ctx.trace.rule(payload)
    except Exception as exc:
        elapsed_ms = round((monotonic() - start) * 1000.0, 3)
        acc.errors.append(f"enrichment: {exc}")
        warning(
            "enrichment failed",
            event_name=ctx.event_name,
            tool_name=ctx.tool_name,
            error=str(exc),
        )
        ctx.trace.rule(_error_trace_payload(identity, "ENRICHMENT", exc, elapsed_ms))


EnforcementMode = Literal["outside_repo", "repo_strict", "repo_relaxed"]


def _resolve_enforcement_mode(ctx: HookContext) -> EnforcementMode:
    repo_cwd = Path(ctx.cwd) if ctx.cwd else Path.cwd()
    repo_root = resolve_repo_root(repo_cwd) or repo_cwd.resolve()

    if not is_repo_enrolled(repo_root):
        return "outside_repo"

    if is_repo_disabled(repo_root):
        return "repo_relaxed"

    return "repo_strict"


def _run_rules(ctx: HookContext, platform: str, mode: EnforcementMode) -> _EvalAccumulator:
    """Build and evaluate applicable rules for the selected enforcement mode."""
    acc = _EvalAccumulator()
    disabled = set(ctx.config.disabled_rules)

    rules: list[Rule] = [*build_always_on_rules(ctx)]
    repo_root = resolve_repo_root(Path(ctx.cwd) if ctx.cwd else Path.cwd())
    effective_root = repo_root or (Path(ctx.cwd) if ctx.cwd else Path.cwd())

    if mode == "repo_strict" and not is_path_skipped(effective_root, ctx.config.skip_paths):
        rules.extend(build_repo_strict_rules(ctx))

    for rule in rules:
        if rule.supports(ctx.event_name) and rule.rule_id not in disabled:
            _run_rule(rule, ctx, platform, acc)
    _safe_enrich(ctx, platform, acc)
    return acc


_REPLAN_PROMPT = (
    "If a hook denies or blocks your change, do not immediately retry the same edit pattern. "
    "Classify the failure first: structural, policy/tooling, or quality. Change approach before retrying. "
    "If the same file or rule is denied twice, stop and make a short repair plan before the next write. "
    "Prefer small helper extractions, params objects, and named constants over large rewrites."
)

_RULE_HINTS: dict[str, str] = {
    "PY-CODE-008": "Next step: extract one helper first; avoid full-file rewrites.",
    "PY-CODE-009": "Next step: introduce a typed params object (dataclass/TypedDict) first.",
    "PY-QUALITY-010": "Next step: define UPPER_CASE constants first, then replace repeated literals.",
    "SHELL-001": "Do not run shell retries. Next step: use structured read/edit/write tools.",
    "PY-SHELL-001": "Do not run shell retries. Next step: use structured read/edit/write tools.",
}


def _failure_class(rule_id: str) -> str:
    if rule_id.startswith("PY-CODE") or rule_id.startswith("PY-QUALITY"):
        return "structural" if rule_id.startswith("PY-CODE") else "quality"
    if "SHELL" in rule_id or rule_id.startswith("GIT-"):
        return "policy_tooling"
    return "quality"


def _finding_path(item: RuleFinding) -> str | None:
    path = item.metadata.get("path")
    if isinstance(path, str) and path:
        return path
    return None


def _denial_findings(findings: list[RuleFinding]) -> list[RuleFinding]:
    return [item for item in findings if item.decision in {"deny", "block"}]


def _dedupe_findings(findings: list[RuleFinding]) -> list[RuleFinding]:
    unique: list[RuleFinding] = []
    seen: set[tuple[str, str | None, str | None, str | None]] = set()
    for item in findings:
        key = (item.rule_id, item.decision, item.message, item.additional_context)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def _filter_search_reminder_dedupe(ctx: HookContext, findings: list[RuleFinding]) -> list[RuleFinding]:
    reminder_indexes = [idx for idx, item in enumerate(findings) if item.rule_id == "REMIND-SEARCH-001"]
    if not reminder_indexes:
        return findings
    if ctx.state.should_emit_search_reminder(ctx.session_id):
        ctx.state.record_search_reminder(ctx.session_id)
        first = reminder_indexes[0]
        return [item for idx, item in enumerate(findings) if item.rule_id != "REMIND-SEARCH-001" or idx == first]
    return [item for item in findings if item.rule_id != "REMIND-SEARCH-001"]


def _apply_loop_aware_steering(ctx: HookContext, findings: list[RuleFinding]) -> None:
    denied = _denial_findings(findings)
    for item in denied:
        path_value = _finding_path(item)
        repeat_count = ctx.state.record_deny_hit(ctx.session_id, item.rule_id, path_value)
        classification = _failure_class(item.rule_id)
        item.metadata["failure_class"] = classification
        item.metadata["repeat_count"] = repeat_count
        if repeat_count >= 2:
            item.metadata["repeat_hit"] = True
            item.message = ((item.message or "").rstrip() + " Change design before retrying.").strip()
            ctx.state.set_retry_lock(ctx.session_id, item.rule_id, path_value, repeat_count)
        if repeat_count >= 3 and item.decision != "block":
            item.decision = "block"
            item.severity = max(item.severity, Severity.HIGH)
            item.metadata["escalated"] = True
        hints = [_REPLAN_PROMPT]
        rule_hint = _RULE_HINTS.get(item.rule_id)
        if rule_hint:
            hints.append(rule_hint)
        if repeat_count >= 2:
            hints.append("Repeated deny detected: write a short repair plan before your next write.")
        item.additional_context = "\n\n".join(
            part for part in [item.additional_context, *hints] if part
        )

    touched_paths = [target.path for target in ctx.content_targets if target.path]
    if touched_paths:
        found_pairs = {
            (item.rule_id, _finding_path(item) or "__pathless__")
            for item in denied
        }
        for path in touched_paths:
            normalized = str((ctx.cwd / path).resolve(strict=False))
            for rule_id in ("PY-CODE-013",):
                key = (rule_id, normalized)
                if key not in found_pairs:
                    ctx.state.clear_deny_hit(ctx.session_id, rule_id, normalized)


def _inject_recent_failure_context(ctx: HookContext, findings: list[RuleFinding]) -> None:
    if ctx.event_name != "SessionStart":
        return
    repeated = ctx.state.recent_repeated_failures(ctx.session_id, limit=4)
    if not repeated:
        return
    lines = ["## Recent repeated failures", "Avoid repeating these patterns this session:"]
    for item in repeated:
        rule_id = item.get("rule_id", "unknown")
        path = item.get("path", "__pathless__")
        count = item.get("count", 0)
        if path == "__pathless__":
            lines.append(f"- {rule_id} x{count}")
        else:
            lines.append(f"- {rule_id} on {Path(str(path)).name} x{count}")
    findings.append(
        RuleFinding(
            rule_id="SESSION-RECENT-FAILURES",
            title="Session repeated-failure memory",
            severity=Severity.LOW,
            additional_context="\n".join(lines),
        )
    )


def _enforce_retry_budget(ctx: HookContext, findings: list[RuleFinding]) -> None:
    if ctx.event_name not in {"PreToolUse", "PermissionRequest"}:
        return
    if not is_edit_like_tool(ctx.tool_name):
        return
    lock = ctx.state.get_retry_lock(ctx.session_id)
    if not lock:
        return
    if ctx.state.has_repair_plan(ctx.session_id):
        ctx.state.clear_retry_lock(ctx.session_id)
        return
    findings.append(
        RuleFinding(
            rule_id="RETRY-BUDGET-001",
            title="Retry budget enforcement",
            severity=Severity.HIGH,
            decision="deny",
            message=(
                "Third write attempt blocked after repeated denies. "
                "Reread the file, name violated constraints, and write a short repair plan first."
            ),
            metadata={
                "rule_id_locked": lock.get("rule_id"),
                "path_locked": lock.get("path"),
                "retry_count": lock.get("count"),
            },
            additional_context=(
                "Required before next write:\n"
                "1) reread the target file\n"
                "2) list violated constraints\n"
                "3) write a short repair plan"
            ),
        )
    )


def _capture_repair_plan_signal(ctx: HookContext) -> None:
    if ctx.event_name not in {"UserPromptSubmit", "SessionStart"}:
        return
    prompt = ctx.user_prompt.lower()
    if "repair plan" not in prompt:
        return
    constraints_named = "constraint" in prompt or "rule" in prompt
    reread_done = "reread" in prompt or "re-read" in prompt or "read" in prompt
    ctx.state.mark_repair_plan(ctx.session_id, constraints_named, reread_done)


def render_output(
    ctx: HookContext,
    findings: list[RuleFinding],
    adapter: PlatformAdapter | None = None,
) -> ObjectDict | None:
    if not findings:
        return None

    adapter = adapter or get_adapter("claude")
    return adapter.render_output(
        ctx.event_name,
        findings,
        context=_collect_context(findings),
        updated_input=_merge_updated_input(findings),
        decision=_top_decision(findings),
    )


def evaluate_payload(
    payload_dict: Mapping[str, object],
    platform: str = "claude",
) -> EngineResult:
    adapter = get_adapter(platform)
    ctx = build_context(adapter.normalize_payload(payload_dict))

    enforcement_mode = _resolve_enforcement_mode(ctx)
    resolved_repo_root = resolve_repo_root(Path(ctx.cwd) if ctx.cwd else Path.cwd())
    capability, degraded_reason = _platform_capability(platform)

    ctx.trace.event(
        {
            "platform": platform,
            "platform_capability": capability,
            "degraded_reason": degraded_reason,
            "event_name": ctx.event_name,
            "session_id": ctx.session_id,
            "tool_name": ctx.tool_name,
            "candidate_paths": ctx.candidate_paths,
            "languages": sorted(ctx.languages),
            "enforcement_mode": enforcement_mode,
            "resolved_repo_root": str(resolved_repo_root) if resolved_repo_root else None,
        }
    )

    _capture_repair_plan_signal(ctx)
    pre_findings: list[RuleFinding] = []
    _enforce_retry_budget(ctx, pre_findings)
    if pre_findings:
        acc = _EvalAccumulator(findings=pre_findings)
    else:
        acc = _run_rules(ctx, platform, enforcement_mode)
    _apply_loop_aware_steering(ctx, acc.findings)
    _inject_recent_failure_context(ctx, acc.findings)
    acc.findings = _filter_search_reminder_dedupe(ctx, acc.findings)
    acc.findings = _dedupe_findings(acc.findings)
    output = render_output(ctx, acc.findings, adapter=adapter)

    ctx.trace.result(
        {
            "platform": platform,
            "platform_capability": capability,
            "degraded_reason": degraded_reason,
            "event_name": ctx.event_name,
            "session_id": ctx.session_id,
            "tool_name": ctx.tool_name,
            "findings": _serialize_findings(acc.findings),
            "errors": acc.errors,
            "output": output,
            "enforcement_mode": enforcement_mode,
            "resolved_repo_root": str(resolved_repo_root) if resolved_repo_root else None,
        }
    )
    return EngineResult(
        event_name=ctx.event_name,
        findings=acc.findings,
        output=output,
        errors=acc.errors,
    )
