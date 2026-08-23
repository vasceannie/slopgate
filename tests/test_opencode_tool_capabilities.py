from __future__ import annotations

import pytest
from hypothesis import given, strategies

from slopgate._types import ObjectDict
from slopgate.opencode_tool_capabilities import (
    OpenCodeToolCapability,
    opencode_tool_allowed_during_repair,
    opencode_tool_capability,
    opencode_tool_is_explicit_repair_command,
)


@pytest.mark.parametrize(
    ("tool_name", "expected"),
    (
        pytest.param("read", OpenCodeToolCapability.READ_ONLY, id="read-only"),
        pytest.param("bash", OpenCodeToolCapability.EFFECTFUL, id="effectful"),
        pytest.param(
            "library-skills_list_skills",
            OpenCodeToolCapability.READ_ONLY,
            id="library-skill-list",
        ),
        pytest.param(
            "library-skills_save_skill",
            OpenCodeToolCapability.EFFECTFUL,
            id="library-skill-save",
        ),
        pytest.param("powershell", None, id="undeclared-shell"),
    ),
)
def test_opencode_tool_capability_uses_exact_declared_ids(
    tool_name: str, expected: OpenCodeToolCapability | None
) -> None:
    assert opencode_tool_capability(tool_name) is expected


@pytest.mark.parametrize(
    "tool_name",
    (
        "agentmemory_memory_diagnose",
        "agentmemory_memory_recall",
        "agentmemory_memory_sessions",
        "agentmemory_memory_smart_search",
        "browser_control",
        "memory_update",
    ),
)
def test_agentmemory_read_tools_remain_allowed_during_repair(tool_name: str) -> None:
    assert opencode_tool_capability(tool_name) is OpenCodeToolCapability.READ_ONLY
    assert opencode_tool_allowed_during_repair(tool_name, {})


@pytest.mark.parametrize(
    ("tool_name", "tool_input", "expected"),
    (
        pytest.param("slopgate_verify_repair", {}, True, id="dedicated-verifier"),
        pytest.param(
            "bash",
            {"command": "slopgate lint check --details --verbose"},
            True,
            id="exact-lint-check",
        ),
        pytest.param(
            "bash",
            {"command": "slopgate lint check && touch bypassed"},
            False,
            id="compound-command",
        ),
        pytest.param(
            "powershell",
            {"command": "slopgate lint check"},
            False,
            id="shell-alias",
        ),
    ),
)
def test_explicit_repair_command_requires_exact_tool_and_tokens(
    tool_name: str, tool_input: ObjectDict, expected: bool
) -> None:
    assert opencode_tool_is_explicit_repair_command(tool_name, tool_input) is expected


@pytest.mark.parametrize(
    "tool_name",
    ("apply_patch", "edit", "write"),
)
def test_exact_file_repair_tools_remain_allowed(tool_name: str) -> None:
    assert opencode_tool_allowed_during_repair(tool_name, {})


@given(
    tool_name=strategies.sampled_from(
        ("read", "apply_patch", "slopgate_verify_repair")
    ),
    prefix=strategies.text(alphabet=" \t", max_size=3),
    suffix=strategies.text(alphabet=" \t", max_size=3),
)
def test_repair_allowlist_normalization_preserves_declared_tools(
    tool_name: str, prefix: str, suffix: str
) -> None:
    assert opencode_tool_allowed_during_repair(
        f"{prefix}{tool_name.upper()}{suffix}", {}
    )
