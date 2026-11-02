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
)

_INVENTORY_PATH = Path(__file__).parents[1] / "docs" / "opencode-tool-inventory.json"


_OPENCODE_TOOL_CAPABILITY_CASES = (
    ("read", OpenCodeToolCapability.READ_ONLY),
    ("background_output", OpenCodeToolCapability.READ_ONLY),
    ("lsp_diagnostics", OpenCodeToolCapability.READ_ONLY),
    ("codegraph_codegraph_explore", OpenCodeToolCapability.READ_ONLY),
    ("bash", OpenCodeToolCapability.EFFECTFUL),
    ("shell", OpenCodeToolCapability.EFFECTFUL),
    ("patch", OpenCodeToolCapability.EFFECTFUL),
    ("execute", OpenCodeToolCapability.EFFECTFUL),
    ("background_cancel", OpenCodeToolCapability.EFFECTFUL),
    ("library-skills_list_skills", OpenCodeToolCapability.READ_ONLY),
    ("library-commands_list_tools", OpenCodeToolCapability.READ_ONLY),
    ("library-skills_save_skill", OpenCodeToolCapability.EFFECTFUL),
    ("opencode_artifact_read", OpenCodeToolCapability.READ_ONLY),
    ("opencode_artifact_create", OpenCodeToolCapability.EFFECTFUL),
    ("opencode_artifact_update", OpenCodeToolCapability.EFFECTFUL),
    ("opencode_artifact_delete", OpenCodeToolCapability.EFFECTFUL),
    ("opencode_schedule_list", OpenCodeToolCapability.READ_ONLY),
    ("opencode_schedule_create", OpenCodeToolCapability.EFFECTFUL),
    ("opencode_schedule_pause", OpenCodeToolCapability.EFFECTFUL),
    ("opencode_schedule_resume", OpenCodeToolCapability.EFFECTFUL),
    ("opencode_schedule_delete", OpenCodeToolCapability.EFFECTFUL),
    ("experimental_image_generate", OpenCodeToolCapability.EFFECTFUL),
    ("powershell", None),
)


@pytest.mark.parametrize(("tool_name", "expected"), _OPENCODE_TOOL_CAPABILITY_CASES)
def test_opencode_tool_capability_classifies_declared_ids(
    tool_name: str, expected: OpenCodeToolCapability | None
) -> None:
    assert opencode_tool_capability(tool_name) is expected


@pytest.mark.parametrize(
    "tool_name",
    ("Read", "READ", "li_st", "Web_Fetch", "LspDiagnostics", "Patch", "BackgroundOutput"),
)
def test_case_and_separator_variants_are_distinct_tools(tool_name: str) -> None:
    assert opencode_tool_capability(tool_name) is None, (
        "V2 tool IDs are exact, so a variant must not inherit a declared capability"
    )
    assert not opencode_tool_allowed_during_repair(tool_name, {}), (
        "a variant of a read-only ID must not pass the repair gate"
    )


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
            "shell",
            {"command": "slopgate lint check --details --verbose"},
            True,
            id="exact-lint-check",
        ),
        pytest.param(
            "shell",
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


def test_code_mode_outer_call_is_allowed_during_repair() -> None:
    assert opencode_tool_allowed_during_repair("execute", {"code": "1"}), (
        "the host gates each inner Code Mode call, so blocking the outer call only "
        "hides read-only tools and the repair verifier"
    )


@pytest.mark.parametrize(
    "tool_name",
    ("patch", "edit", "write"),
)
def test_exact_file_repair_tools_remain_allowed(tool_name: str) -> None:
    assert opencode_tool_allowed_during_repair(tool_name, {})


@pytest.mark.parametrize(
    "command",
    (
        "pwd",
        "readlink src/slopgate",
        "realpath src/slopgate/opencode_tool_capabilities.py",
        "git status --short",
        "git diff -- src/slopgate/opencode_tool_capabilities.py",
        "git show HEAD:README.md",
    ),
)
@pytest.mark.parametrize("tool_name", ("shell", "bash"))
def test_read_only_bash_inspection_remains_allowed(
    command: str, tool_name: str
) -> None:
    assert opencode_tool_allowed_during_repair(tool_name, {"command": command})


@pytest.mark.parametrize(
    "command",
    (
        "pwd && touch bypassed",
        "git status && git commit -am bypassed",
        "git show HEAD:README.md > copied",
    ),
)
@pytest.mark.parametrize("tool_name", ("shell", "bash"))
def test_compound_or_redirected_bash_remains_blocked(
    command: str, tool_name: str
) -> None:
    assert not opencode_tool_allowed_during_repair(tool_name, {"command": command})


@pytest.mark.parametrize("tool_name", ("w_r_i_t_e", "apply__patch"))
def test_repair_allowlist_rejects_separator_collisions(tool_name: str) -> None:
    assert not opencode_tool_allowed_during_repair(tool_name, {})


@given(
    tool_name=strategies.sampled_from(("read", "patch", "slopgate_verify_repair")),
    prefix=strategies.text(alphabet=" \t", max_size=3),
    suffix=strategies.text(alphabet=" \t", max_size=3),
)
def test_repair_allowlist_ignores_only_surrounding_whitespace(
    tool_name: str, prefix: str, suffix: str
) -> None:
    assert opencode_tool_allowed_during_repair(f"{prefix}{tool_name}{suffix}", {})


def test_audited_opencode_inventory_matches_declared_registry() -> None:
    inventory = json.loads(_INVENTORY_PATH.read_text(encoding="utf-8"))

    assert set(inventory["read_only"]) == READ_ONLY_TOOL_IDS, (
        "the audited read-only inventory must match the declared registry"
    )
    assert set(inventory["effectful"]) == EFFECTFUL_TOOL_IDS, (
        "the audited effectful inventory must match the declared registry"
    )
