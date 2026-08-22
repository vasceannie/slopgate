"""Exact OpenCode tool capabilities shared by policy and plugin rendering."""

from __future__ import annotations

from enum import StrEnum
from typing import Final

from slopgate.constants import BASH_TOOL_LOWER


class OpenCodeToolCapability(StrEnum):
    """Trusted effect classes for exact OpenCode tool identifiers."""

    READ_ONLY = "read_only"
    EFFECTFUL = "effectful"


READ_ONLY_TOOL_IDS: Final[frozenset[str]] = frozenset(
    {
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
        "lsp_diagnostics",
        "lsp_find_references",
        "lsp_goto_definition",
        "lsp_prepare_rename",
        "lsp_status",
        "lsp_symbols",
        "list",
        "ls",
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
        "slopgate_verify_repair",
        "todo_write",
        "todowrite",
        "write",
    }
)


def opencode_tool_capability(tool_name: str) -> OpenCodeToolCapability | None:
    """Return the trusted capability for an exact normalized tool identifier."""
    normalized = tool_name.strip().lower()
    if normalized in READ_ONLY_TOOL_IDS:
        return OpenCodeToolCapability.READ_ONLY
    if normalized in EFFECTFUL_TOOL_IDS:
        return OpenCodeToolCapability.EFFECTFUL
    return None


__all__ = [
    "EFFECTFUL_TOOL_IDS",
    "OpenCodeToolCapability",
    "READ_ONLY_TOOL_IDS",
    "opencode_tool_capability",
]
