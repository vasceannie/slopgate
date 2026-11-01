from __future__ import annotations
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from slopgate.context import HookContext
from slopgate.rules.common._shell_read import (
    FullFileReadRule,
    PromptContextRule,
    ProtectedPathsRule,
    _drop_context_sections,
)


def _always_enabled(_ctx: HookContext, _rule_id: str, default: bool = True) -> bool:
    _ = default
    return True


def _make_ctx(
    tool_name: str = "Read",
    candidate_paths: list[str] | None = None,
    shell_command: str | None = None,
    protected_paths: list[str] | None = None,
) -> MagicMock:
    ctx = MagicMock()
    ctx.event_name = "PreToolUse"
    ctx.tool_name = tool_name
    ctx.candidate_paths = candidate_paths or []
    ctx.shell_command = shell_command
    ctx.config.protected_paths = protected_paths or []
    ctx.config.prompt_context_files = []
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
    import slopgate.rules.base

    original = slopgate.rules.base.is_rule_enabled
    setattr(slopgate.rules.base, "is_rule_enabled", _always_enabled)
    try:
        result = rule.evaluate(ctx)
    finally:
        setattr(slopgate.rules.base, "is_rule_enabled", original)
    assert result == []


def test_protected_paths_rule_has_expected_rule_id() -> None:
    rule = ProtectedPathsRule()
    assert rule.rule_id == "BUILTIN-PROTECTED-PATHS"


def test_protected_paths_rule_returns_empty_when_no_patterns_configured() -> None:
    rule = ProtectedPathsRule()
    ctx = _make_ctx(
        tool_name="Write", candidate_paths=["src/app.py"], protected_paths=[]
    )
    import slopgate.rules.base

    original = slopgate.rules.base.is_rule_enabled
    setattr(slopgate.rules.base, "is_rule_enabled", _always_enabled)
    try:
        result = rule.evaluate(ctx)
    finally:
        setattr(slopgate.rules.base, "is_rule_enabled", original)
    assert result == []


def test_protected_paths_rule_denies_matching_path(tmp_path: Path) -> None:
    rule = ProtectedPathsRule()
    target = str(tmp_path / "slopgate.toml")
    ctx = _make_ctx(
        tool_name="Write", candidate_paths=[target], protected_paths=[target]
    )
    ctx.state = MagicMock()
    import slopgate.rules.base

    original_enabled = slopgate.rules.base.is_rule_enabled
    setattr(slopgate.rules.base, "is_rule_enabled", _always_enabled)
    try:
        result = rule.evaluate(ctx)
    finally:
        setattr(slopgate.rules.base, "is_rule_enabled", original_enabled)
    assert len(result) == 1
    assert result[0].rule_id == "BUILTIN-PROTECTED-PATHS"
    assert result[0].decision == "deny"


def test_protected_paths_rule_allows_readonly_sed_of_makefile() -> None:
    rule = ProtectedPathsRule()
    ctx = _make_ctx(
        tool_name="Bash",
        candidate_paths=["Makefile"],
        shell_command="sed -n '1,160p' Makefile",
        protected_paths=["Makefile"],
    )
    import slopgate.rules.base

    original_enabled = slopgate.rules.base.is_rule_enabled
    setattr(slopgate.rules.base, "is_rule_enabled", _always_enabled)
    try:
        result = rule.evaluate(ctx)
    finally:
        setattr(slopgate.rules.base, "is_rule_enabled", original_enabled)
    assert result == []


def test_protected_paths_rule_allows_make_target_execution() -> None:
    rule = ProtectedPathsRule()
    ctx = _make_ctx(
        tool_name="Bash",
        candidate_paths=["Makefile"],
        shell_command="make eval-dataset-ats",
        protected_paths=["Makefile"],
    )
    import slopgate.rules.base

    original_enabled = slopgate.rules.base.is_rule_enabled
    setattr(slopgate.rules.base, "is_rule_enabled", _always_enabled)
    try:
        result = rule.evaluate(ctx)
    finally:
        setattr(slopgate.rules.base, "is_rule_enabled", original_enabled)
    assert result == []


def test_protected_paths_rule_asks_for_makefile_edits() -> None:
    rule = ProtectedPathsRule()
    ctx = _make_ctx(
        tool_name="Write", candidate_paths=["Makefile"], protected_paths=["Makefile"]
    )
    import slopgate.rules.base

    original_enabled = slopgate.rules.base.is_rule_enabled
    setattr(slopgate.rules.base, "is_rule_enabled", _always_enabled)
    try:
        result = rule.evaluate(ctx)
    finally:
        setattr(slopgate.rules.base, "is_rule_enabled", original_enabled)
    assert len(result) == 1, f"expected one protected-path finding, got {result}"
    assert result[0].rule_id == "BUILTIN-PROTECTED-PATHS", (
        f"unexpected rule id: {result[0].rule_id}"
    )
    assert result[0].decision == "ask", (
        f"expected an approval ask, got {result[0].decision}"
    )
    message = result[0].message or ""
    assert "approval" in message.lower(), f"missing approval guidance: {message}"


PROMPT_CONTEXT_BODY = (
    "# Rules\n"
    "- keep me\n"
    "\n"
    "## Before Stopping\n"
    "- run quality\n"
    "\n"
    "## Other\n"
    "- other rule\n"
)


def _prompt_context_text(tmp_path: Path, *, mutated: bool) -> str:
    _ = (tmp_path / "repo.md").write_text(PROMPT_CONTEXT_BODY, encoding="utf-8")
    ctx = _make_ctx()
    ctx.event_name = "UserPromptSubmit"
    ctx.config.prompt_context_files = ["repo.md"]
    ctx.config.root = tmp_path
    ctx.session_id = "prompt-session"
    ctx.state = MagicMock()
    ctx.state.has_session_mutation.return_value = mutated
    import slopgate.rules.base

    original_enabled = slopgate.rules.base.is_rule_enabled
    setattr(slopgate.rules.base, "is_rule_enabled", _always_enabled)
    try:
        findings = PromptContextRule().evaluate(ctx)
    finally:
        setattr(slopgate.rules.base, "is_rule_enabled", original_enabled)
    assert len(findings) == 1, f"expected one prompt context finding, got {findings}"
    return findings[0].additional_context or ""


def test_drop_context_sections_preserves_later_sections() -> None:
    content = "# Rules\n\n## Before Stopping\n- gate\n\n## Keep\n- keep\n"

    dropped = _drop_context_sections(content, ["## Before Stopping"])

    assert dropped == "# Rules\n\n## Keep\n- keep", (
        f"expected only the gated section dropped, got {dropped!r}"
    )


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        pytest.param(
            "# R\n## Before Stopping\n```bash\n# run this\nmake quality\n```\n"
            "- tail\n## Keep\nk",
            "# R\n## Keep\nk",
            id="fenced-comment-inside-dropped-section",
        ),
        pytest.param(
            "# R\n## Example\n```md\n## Before Stopping\n```\nafter\n## Keep\nk",
            "# R\n## Example\n```md\n## Before Stopping\n```\nafter\n## Keep\nk",
            id="fenced-heading-in-kept-section",
        ),
        pytest.param(
            "# R\r\n## Before Stopping  \r\n- gate\r\n## Keep\r\nk",
            "# R\n## Keep\nk",
            id="crlf-and-trailing-space",
        ),
        pytest.param(
            "# R\n- keep\n## Before Stopping\n- gate",
            "# R\n- keep",
            id="section-at-eof",
        ),
    ],
)
def test_drop_context_sections_respects_fences_and_line_endings(
    content: str, expected: str
) -> None:
    dropped = _drop_context_sections(content, ["## Before Stopping"])

    assert dropped == expected, f"unexpected section stripping result: {dropped!r}"


def test_drop_context_sections_without_headings_returns_content() -> None:
    content = "# R\r\n## Before Stopping\r\n- gate"

    dropped = _drop_context_sections(content, ())

    assert dropped is content, "ungated content must pass through unchanged"


@pytest.mark.parametrize(("mutated", "gated"), [(False, False), (True, True)])
def test_prompt_context_rule_gates_stop_quality_section(
    tmp_path: Path, mutated: bool, gated: bool
) -> None:
    context = _prompt_context_text(tmp_path, mutated=mutated)

    assert ("run quality" in context) is gated, (
        f"expected gated={gated} for mutated={mutated}, got {context!r}"
    )
    assert "other rule" in context, (
        f"expected non-gated sections to survive, got {context!r}"
    )
