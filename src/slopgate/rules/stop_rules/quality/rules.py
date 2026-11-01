"""Stop-time quality rules: dismissal blocking and the quality reminder."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from typing_extensions import override

from slopgate.models import RuleFinding, Severity
from slopgate.rules.base import Rule, is_rule_enabled

from .._git_quality import get_stop_response

if TYPE_CHECKING:
    from slopgate.context import HookContext


PREEXISTING_PHRASES = (
    "pre-existing",
    "preexisting",
    "already existed",
    "was already",
    "existed before",
    "not introduced by",
    "outside the scope",
    "out of scope",
    "not my change",
)
DISMISSAL_PHRASE_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(phrase) for phrase in PREEXISTING_PHRASES) + r")\b"
)
MARKDOWN_CODE_RE = re.compile(r"```.*?```|~~~.*?~~~|`[^`\n]*`", re.DOTALL)
SUBAGENT_STOP_EVENT = "SubagentStop"
SUBAGENT_REMINDER_SUFFIX = "#subagent"


def find_dismissal_phrase(response: str) -> str | None:
    """Return the dismissal phrase used in the response's prose.

    Code spans and fences are treated as quotations, so explaining or citing
    the rule does not block the agent's own report. The tradeoff is accepted
    deliberately: a dismissal dressed up as an inline quotation can evade this
    heuristic, which is a speed bump rather than a sandbox. Word boundaries
    keep identifiers like ``*_phrases`` out.
    """
    prose = MARKDOWN_CODE_RE.sub(" ", response.lower())
    match = DISMISSAL_PHRASE_RE.search(prose)
    return match.group(0) if match else None


def reminder_session_key(ctx: HookContext) -> str:
    """Return the dedupe key for the stop reminder scope.

    Subagents share the parent session id, so they need their own key; sharing
    it would spend the parent's one reminder or let every subagent re-remind.
    """
    if ctx.event_name == SUBAGENT_STOP_EVENT:
        return f"{ctx.session_id}{SUBAGENT_REMINDER_SUFFIX}"
    return ctx.session_id


class IgnorePreexistingRule(Rule):
    """Block responses that dismiss issues as pre-existing."""

    rule_id: str = "STOP-001"
    title: str = "Block ignoring pre-existing issues"
    events: tuple[str, ...] = ("Stop", "SubagentStop")

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        phrase = find_dismissal_phrase(get_stop_response(ctx))
        if phrase is None:
            return []
        return [
            RuleFinding(
                rule_id=self.rule_id,
                title=self.title,
                severity=Severity.HIGH,
                decision="block",
                message="Do not dismiss issues as pre-existing. If you found a problem, fix it or explicitly flag it for follow-up.",
                metadata={"matched_phrase": phrase},
            )
        ]


DEFERRED_TEST_INTEGRITY_COMMAND = "slopgate lint test-integrity"
QUALITY_REMINDER = (
    "Before stopping, run quality check `{command}` or report exactly why it cannot run. "
    f"Deferred suite-wide test-integrity collectors run through `{DEFERRED_TEST_INTEGRITY_COMMAND}`."
)


class RequireQualityCheckRule(Rule):
    """Remind to run quality gate before stopping."""

    rule_id: str = "STOP-002"
    title: str = "Require quality check reminder"
    events: tuple[str, ...] = ("Stop", "SubagentStop")

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        if not ctx.state.has_session_mutation(ctx.session_id):
            return []
        session_key = reminder_session_key(ctx)
        if not ctx.state.should_emit_stop_quality_reminder(session_key):
            return []
        if find_dismissal_phrase(get_stop_response(ctx)) is not None:
            return []
        ctx.state.record_stop_quality_reminder(session_key)
        return [
            RuleFinding(
                rule_id=self.rule_id,
                title=self.title,
                severity=Severity.LOW,
                additional_context=QUALITY_REMINDER.format(
                    command=ctx.config.hook_quality_check_command
                ),
            )
        ]
