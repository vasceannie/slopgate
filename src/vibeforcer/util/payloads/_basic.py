from __future__ import annotations

import fnmatch
from collections.abc import Iterable
from pathlib import Path

from vibeforcer._types import ObjectMapping
from vibeforcer.constants import EDIT_TOOL_NAMES, LANGUAGE_BY_SUFFIX, METADATA_PATH
from vibeforcer.util.platform import lower_path_for_match, normalize_path_for_match


def normalize_path(value: str) -> str:
    return normalize_path_for_match(value)


def lower_path(value: str) -> str:
    return lower_path_for_match(value)


def first_present(
    mapping: ObjectMapping, keys: Iterable[str], *, strip: bool = True
) -> str:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip() if strip else value
    return ""


def extract_path_from_mapping(mapping: ObjectMapping) -> str:
    return first_present(
        mapping,
        (
            "resolved_file_path",
            "original_file_path",
            "file_path",
            "filePath",
            METADATA_PATH,
            "relative_path",
            "relativePath",
            "target_file",
            "target_filepath",
            "targetPath",
            "notebook_path",
            "notebookPath",
            "filePath",
        ),
    )


def extract_content_from_mapping(mapping: ObjectMapping) -> str:
    return first_present(
        mapping,
        (
            "new_string",
            "newString",
            "newText",
            "new_text",
            "code_edit",
            "codeEdit",
            "body",
            "new_body",
            "newBody",
            "text",
            "content",
        ),
        strip=False,
    )



def is_edit_like_tool(tool_name: str) -> bool:
    lowered = tool_name.lower()
    if lowered in EDIT_TOOL_NAMES:
        return True
    if "edit_file" in lowered or "editfile" in lowered:
        return True
    if "serena" in lowered:
        return True
    if "morph" in lowered:
        return True
    if "str_replace" in lowered or "strreplace" in lowered:
        return True
    if lowered.endswith("_edit"):
        return True
    return False


def is_bash_tool(tool_name: str) -> bool:
    return shell_kind_for_tool(tool_name) == "bash"


def shell_kind_for_tool(tool_name: str) -> str | None:
    lowered = tool_name.strip().lower().replace("-", "_")
    if lowered in {"bash", "sh", "zsh"}:
        return "bash"
    if lowered in {"powershell", "pwsh", "power_shell"}:
        return "powershell"
    if lowered in {"cmd", "cmd.exe", "command_prompt"}:
        return "cmd"
    if lowered in {"shell", "local_shell", "terminal"}:
        return "unknown"
    return None


def is_shell_tool(tool_name: str) -> bool:
    return shell_kind_for_tool(tool_name) is not None


def detect_language(path_value: str) -> str | None:
    suffix = Path(path_value).suffix.lower()
    return LANGUAGE_BY_SUFFIX.get(suffix)


def path_matches_glob(path_value: str, pattern: str) -> bool:
    normalized_path = lower_path(path_value)
    normalized_pattern = lower_path(pattern)
    basename = Path(normalized_path).name
    if normalized_pattern.endswith("/") and "*" not in normalized_pattern:
        relative_path = normalized_path.removeprefix("./")
        return relative_path.startswith(normalized_pattern) or (
            f"/{normalized_pattern}" in normalized_path
        )
    if "/" not in normalized_pattern:
        return fnmatch.fnmatch(basename, normalized_pattern)
    return fnmatch.fnmatch(normalized_path, normalized_pattern)


def any_path_matches(path_value: str, patterns: list[str]) -> bool:
    if not patterns:
        return True
    return any(path_matches_glob(path_value, pattern) for pattern in patterns)
