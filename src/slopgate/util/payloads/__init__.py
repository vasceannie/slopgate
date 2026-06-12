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
from ._patches import extract_added_patch_content, parse_patch_candidate_paths
from ._payload import HookPayload
from ._shell import shell_command_executable_paths, shell_command_paths
from .targets import (
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
    "any_path_matches",
    "detect_language",
    "direct_candidate_paths",
    "extract_added_patch_content",
    "extract_content_from_mapping",
    "extract_path_from_mapping",
    "first_present",
    "is_bash_tool",
    "is_edit_like_tool",
    "is_shell_tool",
    "lower_path",
    "normalize_path",
    "parse_patch_candidate_paths",
    "path_matches_glob",
    "multi_edit_content_targets",
    "patch_content_targets",
    "shell_command_executable_paths",
    "shell_command_paths",
    "shell_kind_for_tool",
    "tool_input_content_target",
    "tool_input_path",
    "unique_content_targets",
    "lower_path_for_match",
    "normalize_path_for_match",
]
