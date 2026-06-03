from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock


from vibeforcer.rules.common._shell_read import (
    FullFileReadRule,
    PromptContextRule,
    ProtectedPathsRule,
)


def _make_ctx(
    event_name: str = "PreToolUse",
    tool_name: str = "Read",
    candidate_paths: list[str] | None = None,
    shell_command: str | None = None,
    protected_paths: list[str] | None = None,
    prompt_context_files: list[str] | None = None,
) -> MagicMock:
    ctx = MagicMock()
    ctx.event_name = event_name
    ctx.tool_name = tool_name
    ctx.candidate_paths = candidate_paths or []
    ctx.shell_command = shell_command
    ctx.config.protected_paths = protected_paths or []
    ctx.config.prompt_context_files = prompt_context_files or []
    ctx.config.enabled_rules = {}
    ctx.tool_input = {}
    return ctx


def test_prompt_context_rule_has_expected_rule_id() -> None:
    rule = PromptContextRule()

    assert rule.rule_id == "BUILTIN-INJECT-PROMPT"


def test_prompt_context_rule_evaluates_user_prompt_submit_event() -> None:
    rule = PromptContextRule()

    assert "UserPromptSubmit" in rule.events


def test_full_file_read_rule_has_expected_rule_id() -> None:
    rule = FullFileReadRule()

    assert rule.rule_id == "BUILTIN-ENFORCE-FULL-READ"


def test_full_file_read_rule_returns_empty_for_non_read_tool() -> None:
    rule = FullFileReadRule()
    ctx = _make_ctx(tool_name="Write", candidate_paths=["src/app.py"])
    ctx.config.enabled_rules = {}

    import vibeforcer.rules.base as base_mod

    original = base_mod.is_rule_enabled
    base_mod.is_rule_enabled = lambda _ctx, _rule_id: True
    try:
        result = rule.evaluate(ctx)
    finally:
        base_mod.is_rule_enabled = original

    assert result == []


def test_protected_paths_rule_has_expected_rule_id() -> None:
    rule = ProtectedPathsRule()

    assert rule.rule_id == "BUILTIN-PROTECTED-PATHS"


def test_protected_paths_rule_returns_empty_when_no_patterns_configured() -> None:
    rule = ProtectedPathsRule()
    ctx = _make_ctx(
        tool_name="Write",
        candidate_paths=["src/app.py"],
        protected_paths=[],
    )

    import vibeforcer.rules.base as base_mod

    original = base_mod.is_rule_enabled
    base_mod.is_rule_enabled = lambda _ctx, _rule_id: True
    try:
        result = rule.evaluate(ctx)
    finally:
        base_mod.is_rule_enabled = original

    assert result == []


def test_protected_paths_rule_denies_matching_path(tmp_path: Path) -> None:
    rule = ProtectedPathsRule()
    target = str(tmp_path / "quality_gate.toml")
    ctx = _make_ctx(
        tool_name="Write",
        candidate_paths=[target],
        protected_paths=[target],
    )
    ctx.state = MagicMock()

    import vibeforcer.rules.base as base_mod

    original_enabled = base_mod.is_rule_enabled

    base_mod.is_rule_enabled = lambda _ctx, _rule_id: True
    try:
        result = rule.evaluate(ctx)
    finally:
        base_mod.is_rule_enabled = original_enabled

    assert len(result) == 1
    assert result[0].rule_id == "BUILTIN-PROTECTED-PATHS"
