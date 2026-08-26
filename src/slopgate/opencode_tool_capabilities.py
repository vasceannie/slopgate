"""Exact OpenCode tool capabilities shared by policy and plugin rendering."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
import re
import shlex
from typing import Final

from slopgate._types import ObjectMapping
from slopgate.config import GIT_BIN
from slopgate.constants import BASH_TOOL_LOWER, METADATA_COMMAND, METADATA_SLOPGATE
from slopgate.util.payloads import is_safe_read_shell_command


_CAMEL_CASE_BOUNDARY: Final = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_ACRONYM_BOUNDARY: Final = re.compile(r"(?<=[A-Z])(?=[A-Z][a-z])")


def normalize_opencode_tool_id(tool_name: str) -> str:
    """Normalize OpenCode case variants to declared registry IDs."""
    with_acronym_boundaries = _ACRONYM_BOUNDARY.sub("_", tool_name.strip())
    normalized = _CAMEL_CASE_BOUNDARY.sub("_", with_acronym_boundaries).lower()
    if normalized in READ_ONLY_TOOL_IDS or normalized in EFFECTFUL_TOOL_IDS:
        return normalized
    compact = normalized.replace("_", "")
    return _DECLARED_TOOL_IDS_BY_COMPACT.get(compact, normalized)


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
        "background_output",
        "codegraph_codegraph_explore",
        "context7_query-docs",
        "context7_resolve-library-id",
        "find",
        "firecrawl_firecrawl_agent_status",
        "firecrawl_firecrawl_check_crawl_status",
        "firecrawl_firecrawl_developer_search",
        "firecrawl_firecrawl_extract",
        "firecrawl_firecrawl_map",
        "firecrawl_firecrawl_monitor_check",
        "firecrawl_firecrawl_monitor_checks",
        "firecrawl_firecrawl_monitor_get",
        "firecrawl_firecrawl_monitor_list",
        "firecrawl_firecrawl_parse",
        "firecrawl_firecrawl_research_inspect_paper",
        "firecrawl_firecrawl_research_read_paper",
        "firecrawl_firecrawl_research_related_papers",
        "firecrawl_firecrawl_research_search_github",
        "firecrawl_firecrawl_research_search_papers",
        "firecrawl_firecrawl_search",
        "gemini_quota",
        "gitnexus_api_impact",
        "gitnexus_check",
        "gitnexus_context",
        "gitnexus_cypher",
        "gitnexus_detect_changes",
        "gitnexus_explain",
        "gitnexus_group_list",
        "gitnexus_impact",
        "gitnexus_list_repos",
        "gitnexus_pdg_query",
        "gitnexus_query",
        "gitnexus_route_map",
        "gitnexus_shape_check",
        "gitnexus_tool_map",
        "gitnexus_trace",
        "glob",
        "grep",
        "grep_app_search_github",
        "headroom_headroom_retrieve",
        "headroom_headroom_stats",
        "headroom_retrieve",
        "library-commands_get_command",
        "library-commands_get_rule",
        "library-commands_get_tool",
        "library-commands_list_commands",
        "library-commands_list_rules",
        "library-commands_list_tools",
        "library-git_get_mcps",
        "library-git_status",
        "library-skills_get_skill",
        "library-skills_list_skills",
        "list",
        "list_mcp_resource_templates",
        "list_mcp_resources",
        "look_at",
        "ls",
        "lsp",
        "lsp_diagnostics",
        "lsp_find_references",
        "lsp_goto_definition",
        "lsp_prepare_rename",
        "lsp_status",
        "lsp_symbols",
        "question",
        "read",
        "read_mcp_resource",
        "read_session",
        "sequential-thinking_sequentialthinking",
        "session_info",
        "session_list",
        "session_read",
        "session_search",
        "skill",
        "task_get",
        "task_list",
        "webfetch",
        "websearch",
        "websearch_cited",
        "websearch_web_search_exa",
    }
)

EFFECTFUL_TOOL_IDS: Final[frozenset[str]] = frozenset(
    {
        "agentmemory_memory_consolidate",
        "agentmemory_memory_lesson_save",
        "agentmemory_memory_reflect",
        "agentmemory_memory_save",
        "api_delete_resource",
        "apply_patch",
        "background_cancel",
        BASH_TOOL_LOWER,
        "browser_control",
        "edit",
        "firecrawl_firecrawl_agent",
        "firecrawl_firecrawl_crawl",
        "firecrawl_firecrawl_feedback",
        "firecrawl_firecrawl_interact",
        "firecrawl_firecrawl_interact_stop",
        "firecrawl_firecrawl_monitor_create",
        "firecrawl_firecrawl_monitor_delete",
        "firecrawl_firecrawl_monitor_run",
        "firecrawl_firecrawl_monitor_update",
        "firecrawl_firecrawl_scrape",
        "firecrawl_firecrawl_search_feedback",
        "github_update_issue",
        "gitnexus_group_sync",
        "gitnexus_rename",
        "handoff_session",
        "headroom_headroom_compress",
        "interactive_bash",
        "library-commands_delete_command",
        "library-commands_delete_rule",
        "library-commands_delete_tool",
        "library-commands_save_command",
        "library-commands_save_rule",
        "library-commands_save_tool",
        "library-git_commit",
        "library-git_push",
        "library-git_save_mcps",
        "library-git_sync",
        "library-skills_delete_skill",
        "library-skills_save_skill",
        "lsp_install_decision",
        "lsp_rename",
        "memory_update",
        "multi_tool_use.parallel",
        "skill_mcp",
        "slopgate_verify_repair",
        "task",
        "task_create",
        "task_update",
        "todo_write",
        "todowrite",
        "write",
    }
)

_DECLARED_TOOL_IDS_BY_COMPACT: Final[dict[str, str]] = {
    tool_id.replace("-", "").replace("_", ""): tool_id
    for tool_id in (*READ_ONLY_TOOL_IDS, *EFFECTFUL_TOOL_IDS)
}

REPAIR_MUTATION_TOOL_IDS: Final[frozenset[str]] = frozenset(
    {"apply_patch", "edit", "write"}
)
REPAIR_LINT_FLAGS: Final[frozenset[str]] = frozenset({"--details", "--verbose"})
VERIFY_TOOL_ID: Final = "slopgate_verify_repair"
_READ_ONLY_BASH_COMMANDS: Final[frozenset[str]] = frozenset(
    {"pwd", "readlink", "realpath", "which"}
)
_READ_ONLY_GIT_SUBCOMMANDS: Final[frozenset[str]] = frozenset(
    {
        "branch",
        "check-ignore",
        "describe",
        "diff",
        "log",
        "ls-files",
        "remote",
        "rev-parse",
        "show",
        "status",
    }
)


def native_opencode_mutation_tool_id(tool_name: str) -> str | None:
    """Return the native mutation ID without compact separator fallback."""
    with_acronym_boundaries = _ACRONYM_BOUNDARY.sub("_", tool_name.strip())
    normalized = _CAMEL_CASE_BOUNDARY.sub("_", with_acronym_boundaries).lower()
    return normalized if normalized in REPAIR_MUTATION_TOOL_IDS else None


def opencode_tool_capability(tool_name: str) -> OpenCodeToolCapability | None:
    """Return the trusted capability for a normalized tool identifier."""
    normalized = normalize_opencode_tool_id(tool_name)
    if normalized in READ_ONLY_TOOL_IDS:
        return OpenCodeToolCapability.READ_ONLY
    if normalized in EFFECTFUL_TOOL_IDS:
        return OpenCodeToolCapability.EFFECTFUL
    return None


def opencode_tool_is_explicit_repair_command(
    tool_name: str,
    tool_input: ObjectMapping,
) -> bool:
    """Return whether a tool invocation is an approved repair command."""
    normalized = normalize_opencode_tool_id(tool_name)
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


def _is_read_only_bash_command(tool_input: ObjectMapping) -> bool:
    command = next(
        (
            value.strip()
            for key in (METADATA_COMMAND, "cmd", "script")
            if isinstance((value := tool_input.get(key)), str) and value.strip()
        ),
        "",
    )
    if is_safe_read_shell_command(command):
        return True
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    if not tokens or any(token in {";", "&&", "||", "|", ">", ">>"} for token in tokens):
        return False
    executable = Path(tokens[0]).name.lower()
    if executable in _READ_ONLY_BASH_COMMANDS:
        return True
    if executable != GIT_BIN:
        return False
    subcommand = next((token.lower() for token in tokens[1:] if not token.startswith("-")), "")
    return subcommand in _READ_ONLY_GIT_SUBCOMMANDS


def opencode_tool_allowed_during_repair(
    tool_name: str,
    tool_input: ObjectMapping,
) -> bool:
    """Return whether an OpenCode invocation may run during repair."""
    normalized = normalize_opencode_tool_id(tool_name)
    return (
        normalized in READ_ONLY_TOOL_IDS
        or native_opencode_mutation_tool_id(tool_name) is not None
        or (normalized == BASH_TOOL_LOWER and _is_read_only_bash_command(tool_input))
        or opencode_tool_is_explicit_repair_command(tool_name, tool_input)
    )


__all__ = [
    "EFFECTFUL_TOOL_IDS",
    "OpenCodeToolCapability",
    "READ_ONLY_TOOL_IDS",
    "REPAIR_LINT_FLAGS",
    "REPAIR_MUTATION_TOOL_IDS",
    "VERIFY_TOOL_ID",
    "native_opencode_mutation_tool_id",
    "normalize_opencode_tool_id",
    "opencode_tool_allowed_during_repair",
    "opencode_tool_capability",
    "opencode_tool_is_explicit_repair_command",
]
