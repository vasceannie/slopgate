"""Claude CLI retry-feedback helpers for teammate events."""

from __future__ import annotations

from slopgate.constants import BLOCK, DENY
from slopgate.models import EngineResult, RuleFinding
from slopgate.rules.base import join_messages

CLAUDE_TEAM_RETRY_EVENTS = frozenset({"TaskCompleted", "TeammateIdle"})
RETRY_DECISIONS = frozenset({BLOCK, DENY, "ask"})


def claude_team_event_feedback(result: EngineResult) -> str | None:
    """Return stderr feedback for Claude teammate retry events, if blocked."""
    if result.event_name not in CLAUDE_TEAM_RETRY_EVENTS:
        return None
    blocking_findings = [
        finding for finding in result.findings if finding.decision in RETRY_DECISIONS
    ]
    if not blocking_findings:
        return None
    message = join_messages(blocking_findings).strip()
    context = _join_unique_context(blocking_findings)
    feedback = "\n\n".join(part for part in (message, context) if part)
    if feedback:
        return feedback
    rule_ids = ", ".join(finding.rule_id for finding in blocking_findings)
    return f"slopgate blocked {result.event_name}: {rule_ids}"


def _join_unique_context(findings: list[RuleFinding]) -> str:
    parts = [
        finding.additional_context for finding in findings if finding.additional_context
    ]
    return "\n\n".join(dict.fromkeys(parts))
