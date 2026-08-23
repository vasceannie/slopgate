"""Exact OpenCode tool capabilities shared by policy and plugin rendering."""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from slopgate._types import ObjectMapping
from slopgate.constants import BASH_TOOL_LOWER, METADATA_COMMAND, METADATA_SLOPGATE


class OpenCodeToolCapability(StrEnum):
    """Trusted effect classes for exact OpenCode tool identifiers."""

    READ_ONLY = "read_only"
    EFFECTFUL = "effectful"


READ_ONLY_TOOL_IDS: Final[frozenset[str]] = frozenset(
    {
        "agentmemory_memory_diagnose",
        "agentmemory_memory_recall",
        "agentmemory_memory_sessions",
        "agentmemory_memory_smart_search",
        "browser_control",
        "codegraph_codegraph_explore",
        "find",
        "gitnexus_api_impact",
        "gitnexus_check",
        "gitnexus_context",
        "gitnexus_detect_changes",
        "gitnexus_explain",
        "gitnexus_impact",
        "gitnexus_pdg_query",
        "gitnexus_query",
        "gitnexus_route_map",
        "gitnexus_shape_check",
        "gitnexus_tool_map",
        "glob",
        "grep",
        "lsp",
        "lsp_diagnostics",
        "lsp_find_references",
        "lsp_goto_definition",
        "lsp_prepare_rename",
        "lsp_status",
        "lsp_symbols",
        "library-git_status",
        "library-skills_get_skill",
        "library-skills_list_skills",
        "list",
        "ls",
        "memory_update",
        "question",
        "read",
        "read_mcp_resource",
        "read_session",
        "session_info",
        "session_list",
        "session_read",
        "session_search",
        "skill",
        "webfetch",
        "websearch",
        "websearch_cited",
        "websearch_web_search_exa",
    }
)

EFFECTFUL_TOOL_IDS: Final[frozenset[str]] = frozenset(
    {
        "api_delete_resource",
        "apply_patch",
        BASH_TOOL_LOWER,
        "edit",
        "github_update_issue",
        "library-skills_save_skill",
        "slopgate_verify_repair",
        "task",
        "todo_write",
        "todowrite",
        "write",
    }
)

REPAIR_MUTATION_TOOL_IDS: Final[frozenset[str]] = frozenset(
    {"apply_patch", "edit", "write"}
)
REPAIR_LINT_FLAGS: Final[frozenset[str]] = frozenset({"--details", "--verbose"})
VERIFY_TOOL_ID: Final = "slopgate_verify_repair"


def opencode_tool_capability(tool_name: str) -> OpenCodeToolCapability | None:
    """Return the trusted capability for an exact normalized tool identifier."""
    normalized = tool_name.strip().lower()
    if normalized in READ_ONLY_TOOL_IDS:
        return OpenCodeToolCapability.READ_ONLY
    if normalized in EFFECTFUL_TOOL_IDS:
        return OpenCodeToolCapability.EFFECTFUL
    return None


def opencode_tool_is_explicit_repair_command(
    tool_name: str,
    tool_input: ObjectMapping,
) -> bool:
    """Return whether an exact tool invocation is an approved repair command."""
    normalized = tool_name.strip().lower()
    if normalized == VERIFY_TOOL_ID:
        return True
    if normalized != BASH_TOOL_LOWER:
        return False
    command = next(
        (
            value.strip()
            for key in (METADATA_COMMAND, "cmd", "script")
            if isinstance((value := tool_input.get(key)), str) and value.strip()
        ),
        "",
    )
    tokens = command.split()
    return (
        len(tokens) >= 3
        and tokens[:3] == [METADATA_SLOPGATE, "lint", "check"]
        and all(token in REPAIR_LINT_FLAGS for token in tokens[3:])
    )


def opencode_tool_allowed_during_repair(
    tool_name: str,
    tool_input: ObjectMapping,
) -> bool:
    """Return whether an exact OpenCode invocation may run during repair."""
    normalized = tool_name.strip().lower()
    return (
        normalized in READ_ONLY_TOOL_IDS
        or normalized in REPAIR_MUTATION_TOOL_IDS
        or opencode_tool_is_explicit_repair_command(tool_name, tool_input)
    )


__all__ = [
    "EFFECTFUL_TOOL_IDS",
    "OpenCodeToolCapability",
    "READ_ONLY_TOOL_IDS",
    "REPAIR_LINT_FLAGS",
    "REPAIR_MUTATION_TOOL_IDS",
    "VERIFY_TOOL_ID",
    "opencode_tool_allowed_during_repair",
    "opencode_tool_capability",
    "opencode_tool_is_explicit_repair_command",
]
