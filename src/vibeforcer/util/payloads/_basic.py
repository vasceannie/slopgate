from __future__ import annotations

import fnmatch
from collections.abc import Iterable
from pathlib import Path

from vibeforcer._types import ObjectMapping
from vibeforcer.constants import EDIT_TOOL_NAMES, LANGUAGE_BY_SUFFIX, METADATA_PATH

def normalize_path(value: str) -> str:
    normalized = value.replace("\\", "/")
    return normalized.strip()


def lower_path(value: str) -> str:
    normalized = normalize_path(value)
    return normalized.lower()


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
    return tool_name.lower() == "bash"


def detect_language(path_value: str) -> str | None:
    suffix = Path(path_value).suffix.lower()
    return LANGUAGE_BY_SUFFIX.get(suffix)


def path_matches_glob(path_value: str, pattern: str) -> bool:
    normalized_path = lower_path(path_value)
    normalized_pattern = lower_path(pattern)
    basename = Path(normalized_path).name
    if normalized_pattern.endswith("/") and "*" not in normalized_pattern:
        return normalized_path.startswith(normalized_pattern)
    if "/" not in normalized_pattern:
        return fnmatch.fnmatch(basename, normalized_pattern)
    return fnmatch.fnmatch(normalized_path, normalized_pattern)


def any_path_matches(path_value: str, patterns: list[str]) -> bool:
    if not patterns:
        return True
    return any(path_matches_glob(path_value, pattern) for pattern in patterns)
