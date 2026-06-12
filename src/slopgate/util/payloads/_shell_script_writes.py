from __future__ import annotations

import re

from ._shell_paths import SCRIPT_PATH_TEXT, append_unique_shell_path


_SCRIPT_QUOTED_PATH_TEXT = rf"['\"]({SCRIPT_PATH_TEXT})['\"]"
_PYTHON_PATH_WRITE_RE = re.compile(
    rf"(?:pathlib\.)?path\(\s*{_SCRIPT_QUOTED_PATH_TEXT}\s*\)\."
    r"(?:write_text|write_bytes)\s*\(",
    re.IGNORECASE,
)
_PYTHON_OPEN_WRITE_RE = re.compile(
    rf"\bopen\(\s*{_SCRIPT_QUOTED_PATH_TEXT}\s*,\s*"
    r"['\"][^'\"]*[wax+][^'\"]*['\"]",
    re.IGNORECASE,
)
_PYTHON_OS_OPEN_WRITE_RE = re.compile(
    rf"\bos\.open\(\s*{_SCRIPT_QUOTED_PATH_TEXT}\s*,[^)]*"
    r"\bos\.O_(?:WRONLY|RDWR|CREAT|TRUNC|APPEND)\b",
    re.IGNORECASE,
)
_NODE_WRITE_RE = re.compile(
    rf"\b(?:(?:require\(\s*['\"]fs['\"]\s*\)|fs|deno|file)\.)"
    rf"(?:write(?:file|filesync)?|append(?:file|filesync)?)\(\s*"
    rf"{_SCRIPT_QUOTED_PATH_TEXT}",
    re.IGNORECASE,
)
_SCRIPT_WRITE_PATTERNS = (
    _PYTHON_PATH_WRITE_RE,
    _PYTHON_OPEN_WRITE_RE,
    _PYTHON_OS_OPEN_WRITE_RE,
    _NODE_WRITE_RE,
)


def script_api_write_paths(command: str) -> list[str]:
    seen: list[str] = []
    for pattern in _SCRIPT_WRITE_PATTERNS:
        for match in pattern.finditer(command):
            append_unique_shell_path(seen, match.group(1))
    return seen
