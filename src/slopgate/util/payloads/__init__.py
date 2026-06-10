from __future__ import annotations

__all__ = [
    "HookPayload",
    "any_path_matches",
    "detect_language",
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
    "shell_command_executable_paths",
    "shell_command_paths",
    "shell_kind_for_tool",
    "lower_path_for_match",
    "normalize_path_for_match",
]
from slopgate.util.platform import lower_path_for_match, normalize_path_for_match

lower_path = lower_path_for_match
normalize_path = normalize_path_for_match
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

__all__ = [
    "HookPayload",
    "any_path_matches",
    "detect_language",
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
    "shell_command_executable_paths",
    "shell_command_paths",
    "shell_kind_for_tool",
]
