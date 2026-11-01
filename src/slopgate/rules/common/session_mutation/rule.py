"""Post-tool rule that records session code mutations."""

from __future__ import annotations

from typing import TYPE_CHECKING

from typing_extensions import override

from slopgate.constants import POST_TOOL_USE
from slopgate.models import RuleFinding
from slopgate.rules.base import Rule, is_rule_enabled
from slopgate.util.payloads import is_mutating_tool_use

if TYPE_CHECKING:
    from slopgate.context import HookContext


class SessionMutationTrackingRule(Rule):
    """Record that the session performed a mutating tool use."""

    rule_id: str = "BUILTIN-TRACK-MUTATION"
    title: str = "Track session code mutations"
    events: tuple[str, ...] = (POST_TOOL_USE,)

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        if not is_mutating_tool_use(ctx):
            return []
        ctx.state.record_session_mutation(ctx.session_id, ctx.tool_name)
        return []
