from __future__ import annotations

from ._basic import (
    any_path_matches,
    detect_language,
    extract_content_from_mapping,
    extract_path_from_mapping,
    first_present,
    is_bash_tool,
    is_edit_like_tool,
    is_shell_tool,
    path_matches_glob,
    shell_kind_for_tool,
)
from ._intent import (
    ToolIntent,
    candidate_path_source,
    is_mutating_tool_use,
    is_read_only_tool_use,
    platform_event_name,
    tool_intent,
    tool_intent_reason,
)
from ._patches import extract_added_patch_content, parse_patch_candidate_paths
from ._payload import HookPayload
from ._shell import (
    FIND_MUTATING_ACTIONS,
    command_has_word,
    find_command_has_mutation,
    is_mutating_shell_command,
    is_safe_read_shell_command,
    script_write_paths,
    shell_command_executable_paths,
    shell_command_paths,
    shell_tokens,
)
from ._shell_content import shell_content_targets
from ._shell_paths import shell_write_redirection_paths
from .targets import (
    ctx_execute_content_target,
    direct_candidate_paths,
    multi_edit_content_targets,
    patch_content_targets,
    tool_input_content_target,
    tool_input_path,
    unique_content_targets,
)
from slopgate.util.platform import lower_path_for_match, normalize_path_for_match

lower_path = lower_path_for_match
normalize_path = normalize_path_for_match

__all__ = [
    "HookPayload",
    "ToolIntent",
    "any_path_matches",
    "candidate_path_source",
    "command_has_word",
    "ctx_execute_content_target",
    "FIND_MUTATING_ACTIONS",
    "detect_language",
    "direct_candidate_paths",
    "extract_added_patch_content",
    "extract_content_from_mapping",
    "extract_path_from_mapping",
    "find_command_has_mutation",
    "first_present",
    "is_bash_tool",
    "is_edit_like_tool",
    "is_mutating_shell_command",
    "is_mutating_tool_use",
    "is_read_only_tool_use",
    "is_safe_read_shell_command",
    "is_shell_tool",
    "lower_path",
    "normalize_path",
    "parse_patch_candidate_paths",
    "path_matches_glob",
    "platform_event_name",
    "script_write_paths",
    "multi_edit_content_targets",
    "patch_content_targets",
    "shell_command_executable_paths",
    "shell_command_paths",
    "shell_content_targets",
    "shell_write_redirection_paths",
    "shell_kind_for_tool",
    "shell_tokens",
    "tool_intent",
    "tool_intent_reason",
    "tool_input_content_target",
    "tool_input_path",
    "unique_content_targets",
    "lower_path_for_match",
    "normalize_path_for_match",
]
