"""Retry-adjacent finding deduplication helpers."""

from __future__ import annotations

from slopgate.context import HookContext
from slopgate.models import RuleFinding


def dedupe_findings(findings: list[RuleFinding]) -> list[RuleFinding]:
    unique_by_key = {
        (item.rule_id, item.decision, item.message, item.additional_context): item
        for item in reversed(findings)
    }
    return list(reversed(unique_by_key.values()))


def filter_search_reminder_dedupe(
    ctx: HookContext, findings: list[RuleFinding]
) -> list[RuleFinding]:
    indexes = [
        index
        for index, item in enumerate(findings)
        if item.rule_id == "REMIND-SEARCH-001"
    ]
    if not indexes:
        return findings
    if ctx.state.should_emit_search_reminder(ctx.session_id):
        ctx.state.record_search_reminder(ctx.session_id)
        first = indexes[0]
        return [
            item
            for index, item in enumerate(findings)
            if item.rule_id != "REMIND-SEARCH-001" or index == first
        ]
    return [item for item in findings if item.rule_id != "REMIND-SEARCH-001"]
