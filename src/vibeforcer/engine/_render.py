from __future__ import annotations

from vibeforcer._types import ObjectDict
from vibeforcer.adapters import get_adapter
from vibeforcer.adapters.base import PlatformAdapter
from vibeforcer.constants import DENY
from vibeforcer.context import HookContext
from vibeforcer.models import RuleFinding

DECISION_ORDER: dict[str | None, int] = {
    DENY: 4,
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
    contextual = [item for item in findings if item.additional_context]
    if not contextual:
        return None
    if not any(item.decision in {DENY, "block", "ask"} for item in contextual):
        parts = [item.additional_context for item in contextual if item.additional_context]
        return "\n\n".join(dict.fromkeys(parts))
    immediate_parts = [
        item.additional_context
        for item in contextual
        if item.additional_context and item.decision in {DENY, "block", "ask"}
    ]
    advisory_parts = [
        item.additional_context
        for item in contextual
        if item.additional_context and item.decision not in {DENY, "block", "ask"}
    ]
    parts = list(dict.fromkeys(immediate_parts))
    advisory = "\n\n".join(dict.fromkeys(advisory_parts))
    if advisory:
        parts.append(
            "Later design debt / not the immediate unblock action:\n" + advisory
        )
    return "\n\n".join(parts) if parts else None


def _top_decision(findings: list[RuleFinding]) -> str | None:
    if not findings:
        return None
    return max(findings, key=_finding_sort_key).decision

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
