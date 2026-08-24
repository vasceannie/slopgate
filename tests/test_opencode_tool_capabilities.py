from __future__ import annotations

import json
from pathlib import Path

import pytest
from hypothesis import given, strategies

from slopgate._types import ObjectDict
from slopgate.opencode_tool_capabilities import (
    EFFECTFUL_TOOL_IDS,
    OpenCodeToolCapability,
    READ_ONLY_TOOL_IDS,
    opencode_tool_allowed_during_repair,
    opencode_tool_capability,
    opencode_tool_is_explicit_repair_command,
    normalize_opencode_tool_id,
)

_INVENTORY_PATH = Path(__file__).parents[1] / "docs" / "opencode-tool-inventory.json"


_OPENCODE_TOOL_CAPABILITY_CASES = (
    ("read", OpenCodeToolCapability.READ_ONLY),
    ("BackgroundOutput", OpenCodeToolCapability.READ_ONLY),
    ("LspDiagnostics", OpenCodeToolCapability.READ_ONLY),
    ("CodegraphCodegraphExplore", OpenCodeToolCapability.READ_ONLY),
    ("bash", OpenCodeToolCapability.EFFECTFUL),
    ("ApplyPatch", OpenCodeToolCapability.EFFECTFUL),
    ("BackgroundCancel", OpenCodeToolCapability.EFFECTFUL),
    ("LibraryCommandsListTools", OpenCodeToolCapability.READ_ONLY),
    ("LibrarySkillsSaveSkill", OpenCodeToolCapability.EFFECTFUL),
    ("library-skills_list_skills", OpenCodeToolCapability.READ_ONLY),
    ("library-commands_list_tools", OpenCodeToolCapability.READ_ONLY),
    ("library-skills_save_skill", OpenCodeToolCapability.EFFECTFUL),
    ("powershell", None),
)


@pytest.mark.parametrize(("tool_name", "expected"), _OPENCODE_TOOL_CAPABILITY_CASES)
def test_opencode_tool_capability_normalizes_declared_ids(
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
    ),
)
def test_agentmemory_read_tools_remain_allowed_during_repair(tool_name: str) -> None:
    assert opencode_tool_capability(tool_name) is OpenCodeToolCapability.READ_ONLY
    assert opencode_tool_allowed_during_repair(tool_name, {})


@pytest.mark.parametrize("tool_name", ("browser_control", "memory_update"))
def test_mutation_capable_legacy_tools_are_effectful(tool_name: str) -> None:
    assert opencode_tool_capability(tool_name) is OpenCodeToolCapability.EFFECTFUL
    assert not opencode_tool_allowed_during_repair(tool_name, {})


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


@pytest.mark.parametrize(
    ("tool_name", "expected"),
    (
        pytest.param("LspDiagnostics", "lsp_diagnostics", id="pascal-case"),
        pytest.param(
            "CodegraphCodegraphExplore",
            "codegraph_codegraph_explore",
            id="multiword-pascal-case",
        ),
        pytest.param("ApplyPatch", "apply_patch", id="camel-case"),
        pytest.param(
            "LibraryCommandsListTools",
            "library-commands_list_tools",
            id="structured-pascal-case",
        ),
        pytest.param(
            "library-commands_list_tools",
            "library-commands_list_tools",
            id="structured-tool-id",
        ),
    ),
)
def test_normalize_opencode_tool_id_preserves_declared_shape(
    tool_name: str, expected: str
) -> None:
    assert normalize_opencode_tool_id(tool_name) == expected


def test_audited_opencode_inventory_matches_declared_registry() -> None:
    inventory = json.loads(_INVENTORY_PATH.read_text(encoding="utf-8"))
    read_only = {
        normalize_opencode_tool_id(tool_id) for tool_id in inventory["read_only"]
    }
    effectful = {
        normalize_opencode_tool_id(tool_id) for tool_id in inventory["effectful"]
    }

    assert read_only == READ_ONLY_TOOL_IDS
    assert effectful == EFFECTFUL_TOOL_IDS
