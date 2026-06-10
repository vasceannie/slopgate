from __future__ import annotations
from unittest.mock import MagicMock
from slopgate.context import HookContext
from slopgate.models import RuleFinding
from slopgate.rules.python_ast._helpers import (
    decision_for_context,
    detect_family_prefix,
    evaluate_common,
)


def test_decision_for_context_returns_deny_for_pre_tool_use() -> None:
    ctx = MagicMock()
    ctx.event_name = "PreToolUse"
    result = decision_for_context(ctx)
    assert result == "deny"


def test_decision_for_context_returns_deny_for_permission_request() -> None:
    ctx = MagicMock()
    ctx.event_name = "PermissionRequest"
    result = decision_for_context(ctx)
    assert result == "deny"


def test_decision_for_context_returns_block_for_post_tool_use() -> None:
    ctx = MagicMock()
    ctx.event_name = "PostToolUse"
    result = decision_for_context(ctx)
    assert result == "block"


def test_detect_family_prefix_returns_prefix_for_three_or_more_names() -> None:
    names = ["parse_user", "parse_config", "parse_event"]
    result = detect_family_prefix(names)
    assert result == "parse_"


def test_detect_family_prefix_returns_none_for_fewer_than_three() -> None:
    names = ["parse_user", "parse_config", "build_thing"]
    result = detect_family_prefix(names)
    assert result is None


def test_detect_family_prefix_returns_none_for_empty_list() -> None:
    assert detect_family_prefix([]) is None


def _evaluate_common_when_rule_disabled() -> list[RuleFinding]:
    from slopgate.rules.base import Rule

    def _no_findings(_src: object, _path: object, _ctx: object) -> list[RuleFinding]:
        return []

    class _StubRule(Rule):
        rule_id: str = "TEST-RULE-999"
        title: str = "stub"
        events: tuple[str, ...] = ("PreToolUse",)

        def evaluate(self, ctx: object) -> list[RuleFinding]:
            return []

    ctx_patch = MagicMock()
    ctx_patch.event_name = "PreToolUse"
    ctx_patch.config.python_ast_enabled = True
    ctx_patch.config.enabled_rules = {}
    import slopgate.rules.base

    original = slopgate.rules.base.is_rule_enabled

    def _always_disabled(
        _ctx: HookContext, _rule_id: str, default: bool = True
    ) -> bool:
        _ = default
        return False

    setattr(slopgate.rules.base, "is_rule_enabled", _always_disabled)
    try:
        return evaluate_common(_StubRule(), ctx_patch, _no_findings)
    finally:
        setattr(slopgate.rules.base, "is_rule_enabled", original)


def test_evaluate_common_returns_empty_when_rule_disabled() -> None:
    assert _evaluate_common_when_rule_disabled() == []
