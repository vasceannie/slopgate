"""Third-attempt semantic retry enforcement and read-evidence capture."""

from __future__ import annotations

from dataclasses import dataclass

from slopgate._types import ObjectDict, string_value
from slopgate.constants import (
    BLOCK,
    CONTEXT,
    DENY,
    PERMISSION_REQUEST,
    POST_TOOL_USE,
    PRE_TOOL_USE,
    WARN,
)
from slopgate.context import HookContext
from slopgate.models import RuleFinding, Severity
from slopgate.util.payloads import is_edit_like_tool

from .._hints import retry_budget_relevant_denials
from .guidance import recovery_guidance
from .identity import (
    attempt_fingerprint,
    normalize_attempt_path,
    semantic_enforcement_key,
)

RETRY_BUDGET_RULE_ID = "RETRY-BUDGET-001"


@dataclass(frozen=True, slots=True)
class _BudgetMatch:
    repo_root: str
    locks: dict[str, ObjectDict]
    rule_ids: tuple[str, ...]
    guidance_rule: str


def record_full_read_evidence(ctx: HookContext) -> None:
    if ctx.event_name != POST_TOOL_USE:
        return
    if ctx.tool_name != "Read":
        return
    if "offset" in ctx.tool_input or "limit" in ctx.tool_input:
        return
    for path in ctx.candidate_paths:
        if path:
            ctx.state.record_retry_full_read(
                ctx.session_id, normalize_attempt_path(ctx, path)
            )


def capture_repair_plan_signal(ctx: HookContext) -> None:
    """Compatibility no-op: prompt prose is never recovery evidence."""
    _ = ctx


def _budget_match(ctx: HookContext, findings: list[RuleFinding]) -> _BudgetMatch | None:
    denied = retry_budget_relevant_denials(findings)
    if not denied:
        return None
    current = [(item, semantic_enforcement_key(ctx, item)) for item in denied]
    repo_root = current[0][1].repo_root
    active = ctx.state.active_semantic_retry_locks(ctx.session_id, repo_root)
    locks: dict[str, ObjectDict] = {}
    matched_items: list[RuleFinding] = []
    for item, key in current:
        raw_key = ctx.state.semantic_state_key(key)
        lock = active.get(raw_key)
        if lock is not None:
            locks[raw_key] = lock
            matched_items.append(item)
    if not matched_items:
        return None
    return _BudgetMatch(
        repo_root=repo_root,
        locks=locks,
        rule_ids=tuple(sorted({item.rule_id for item in matched_items})),
        guidance_rule=matched_items[0].rule_id,
    )


def _budget_action(ctx: HookContext) -> str | None:
    surface = ctx.config.rule_surfaces.get(RETRY_BUDGET_RULE_ID)
    if surface is not None and surface.hook.enabled is False:
        return None
    if ctx.config.enabled_rules.get(RETRY_BUDGET_RULE_ID) is False:
        return None
    return (surface.hook.action or DENY) if surface is not None else DENY


def _budget_finding(
    ctx: HookContext, match: _BudgetMatch, status: str, action: str
) -> RuleFinding:
    guidance = recovery_guidance(match.guidance_rule)
    blocking = action in {BLOCK, DENY}
    fingerprints = sorted(
        {
            fingerprint
            for lock in match.locks.values()
            if (fingerprint := string_value(lock.get("attempt_fingerprint")))
            is not None
        }
    )
    retry_count = max(
        (
            count
            for lock in match.locks.values()
            if isinstance((count := lock.get("count")), int)
        ),
        default=2,
    )
    return RuleFinding(
        rule_id=RETRY_BUDGET_RULE_ID,
        title="Semantic retry budget enforcement",
        severity=Severity.HIGH,
        decision=DENY if blocking else None,
        message=(
            "Third semantic edit attempt blocked pending structured changed-design evidence."
            if blocking
            else None
        ),
        metadata={
            "matched_rule_ids": list(match.rule_ids),
            "semantic_keys": sorted(match.locks),
            "attempt_fingerprints_locked": fingerprints,
            "attempt_fingerprint_current": attempt_fingerprint(ctx),
            "semantic_retry_count": retry_count,
            "recovery_status": status,
            "recovery_guidance_id": guidance.guidance_id,
            "recovery_guidance_conflicts": list(guidance.conflicts),
            "rollout": action,
        },
        additional_context=guidance.text if action in {CONTEXT, WARN} else None,
    )


def enforce_retry_budget(ctx: HookContext, findings: list[RuleFinding]) -> None:
    if ctx.event_name not in {PRE_TOOL_USE, PERMISSION_REQUEST}:
        return
    if not is_edit_like_tool(ctx.tool_name):
        return
    action = _budget_action(ctx)
    if action is None:
        return
    match = _budget_match(ctx, findings)
    if match is None:
        return
    consumed, status = ctx.state.use_recovery_evidence(ctx.session_id, match.repo_root)
    if not consumed:
        findings.append(_budget_finding(ctx, match, status, action))
