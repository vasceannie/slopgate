from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from time import monotonic
from typing import Literal

from slopgate.constants import (
    CONTEXT,
    WARN,
    SESSION_ID,
    PLATFORM_OPENCODE,
    PLATFORM_CODEX,
    UNKNOWN_VALUE,
)
from slopgate.config import (
    is_path_skipped,
    is_repo_disabled,
    is_repo_enrolled,
    resolve_repo_root,
)
from slopgate.context import HookContext
from slopgate.enrichment import enrich_findings
from slopgate.models import RuleFinding, Severity
from slopgate.rules import build_always_on_rules, build_repo_strict_rules
from slopgate.rules.base import Rule
from slopgate.util import warning


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


def _hook_surface_allows_event(rule: Rule, ctx: HookContext) -> bool:
    surface = ctx.config.rule_surfaces.get(rule.rule_id)
    if surface is None or not surface.hook.events:
        return True
    return ctx.event_name in surface.hook.events


def _hook_surface_enabled(rule: Rule, ctx: HookContext) -> bool:
    surface = ctx.config.rule_surfaces.get(rule.rule_id)
    if surface is not None and surface.hook.enabled is not None:
        return surface.hook.enabled
    value = ctx.config.enabled_rules.get(rule.rule_id)
    return rule.enabled if value is None else value


def _apply_hook_surface_action(ctx: HookContext, findings: list[RuleFinding]) -> None:
    for finding in findings:
        surface = ctx.config.rule_surfaces.get(finding.rule_id)
        action = surface.hook.action if surface is not None else None
        if action is None:
            continue
        if action in {CONTEXT, WARN}:
            finding.decision = None
        else:
            finding.decision = action
        finding.metadata["surface_action"] = action


def _trace_identity(ctx: HookContext, platform: str) -> dict[str, object]:
    return {
        "platform": platform,
        "event_name": ctx.event_name,
        SESSION_ID: ctx.session_id,
        "tool_name": ctx.tool_name,
    }


def platform_capability(platform: str) -> tuple[str, str | None]:
    normalized = platform.strip().lower()
    if normalized == PLATFORM_OPENCODE:
        return (
            "degraded",
            "opencode uses plugin events rather than Claude-style hooks; prompt interception is unavailable, stop blocking is advisory, and post-tool deny is best-effort",
        )
    if normalized == PLATFORM_CODEX:
        return (
            "partial",
            "codex hooks are experimental and currently provide Bash-focused tool interception rather than Claude-style tool parity",
        )
    if normalized == "cursor":
        return (
            "partial",
            "cursor postToolUse and afterFileEdit cannot hard-block tool results; they inject additional_context only. workspaceOpen and several observational hooks are not installed by default",
        )
    if normalized == UNKNOWN_VALUE:
        return (
            UNKNOWN_VALUE,
            "hook platform was omitted or could not be proven; Slopgate used compatibility parsing without assigning Claude provenance",
        )
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
class EvalAccumulator:
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
    acc: EvalAccumulator,
) -> None:
    """Evaluate a single rule, collecting findings and errors."""
    identity = _trace_identity(ctx, platform)
    start = monotonic()
    try:
        result = rule.evaluate(ctx)
        elapsed_ms = round((monotonic() - start) * 1000.0, 3)
        if not result:
            return
        _apply_hook_surface_action(ctx, result)
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
    acc: EvalAccumulator,
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


def resolve_enforcement_mode(ctx: HookContext) -> EnforcementMode:
    repo_cwd = Path(ctx.cwd) if ctx.cwd else Path.cwd()
    repo_root = resolve_repo_root(repo_cwd) or repo_cwd.resolve()

    if not is_repo_enrolled(repo_root):
        return "outside_repo"

    if is_repo_disabled(repo_root):
        return "repo_relaxed"

    return "repo_strict"


def run_rules(
    ctx: HookContext, platform: str, mode: EnforcementMode
) -> EvalAccumulator:
    """Build and evaluate applicable rules for the selected enforcement mode."""
    acc = EvalAccumulator()
    disabled = set(ctx.config.disabled_rules)

    rules: list[Rule] = [*build_always_on_rules(ctx)]
    repo_root = resolve_repo_root(Path(ctx.cwd) if ctx.cwd else Path.cwd())
    effective_root = repo_root or (Path(ctx.cwd) if ctx.cwd else Path.cwd())

    if mode == "repo_strict" and not is_path_skipped(
        effective_root, ctx.config.skip_paths
    ):
        rules.extend(build_repo_strict_rules(ctx))

    for rule in rules:
        if (
            rule.rule_id not in disabled
            and _hook_surface_enabled(rule, ctx)
            and rule.supports(ctx.event_name)
            and _hook_surface_allows_event(rule, ctx)
        ):
            _run_rule(rule, ctx, platform, acc)
    _safe_enrich(ctx, platform, acc)
    return acc
