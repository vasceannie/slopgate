from __future__ import annotations

import re
import shlex
from pathlib import Path

def _is_shell_glob_token(value: str) -> bool:
    """Return True when a shell token is a glob pattern, not a literal path."""
    return any(char in value for char in "*?[")


_COMMAND_SEPARATORS = frozenset({"&&", "||", ";", "|"})
_COMMAND_WRAPPER_NAMES = frozenset({"env", "command", "builtin", "exec", "time", "nohup"})
_SHELL_REDIRECTION_PATTERN = re.compile(r"(?:\d*>>?|\d*<)\s*([^\s;|&]+)")
_SHELL_PATHISH_PATTERN = re.compile(
    r"(?:[A-Za-z]:[\\/])?(?:[~./\\A-Za-z0-9_-]+[/\\])*[A-Za-z0-9_.-]+\.[A-Za-z0-9]+"
)
_SHELL_KNOWN_FILENAMES = frozenset(
    {
        "makefile",
        "dockerfile",
        "readme",
        "license",
        "pyproject.toml",
        "package.json",
        "tsconfig.json",
    }
)
_SHELL_TEXT_OPTION_NAMES = frozenset(
    {"--reason", "--message", "--description", "--comment", "--title"}
)


def _is_leading_shell_assignment(value: str) -> bool:
    """Return True for NAME=value tokens that can appear before a command."""
    if "=" not in value or value.startswith("-"):
        return False
    name, _ = value.split("=", 1)
    return bool(name) and name.replace("_", "").isalnum() and "/" not in name


def _shell_command_executable_indexes(tokens: list[str]) -> set[int]:
    """Return indexes that represent command executables, not file targets."""
    indexes: set[int] = set()
    expecting_command = True
    for index, token in enumerate(tokens):
        cleaned = token.strip("\"'")
        if cleaned in _COMMAND_SEPARATORS:
            expecting_command = True
            continue
        if not expecting_command:
            continue
        if not cleaned or cleaned.startswith((">", "<")):
            continue
        if cleaned.startswith("-") or _is_leading_shell_assignment(cleaned):
            continue
        basename = Path(cleaned).name.lower()
        if basename in _COMMAND_WRAPPER_NAMES:
            if "/" in cleaned or cleaned.startswith(("~", "./", "../")):
                indexes.add(index)
            continue
        indexes.add(index)
        expecting_command = False
    return indexes


def shell_command_executable_paths(command: str) -> list[str]:
    """Return path-like executable tokens that appear in command position."""
    tokens = _shell_tokens(command)
    executable_indexes = _shell_command_executable_indexes(tokens)
    return [tokens[index].strip("\"'") for index in sorted(executable_indexes)]


def _shell_tokens(command: str) -> list[str]:
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        return command.split()


def _append_unique_shell_path(seen: list[str], value: str) -> None:
    cleaned_value = value.strip("\"'`")
    if not cleaned_value or _is_shell_glob_token(cleaned_value):
        return
    if cleaned_value.lower() in {"/dev/null", "$null", "nul", "nul:"}:
        return
    if cleaned_value not in seen:
        seen.append(cleaned_value)


def _shell_option_value(cleaned: str) -> str:
    if cleaned.startswith("-"):
        if "=" not in cleaned:
            return ""
        option_name, option_value = cleaned.split("=", 1)
        if option_name.lower() in _SHELL_TEXT_OPTION_NAMES:
            return ""
        return option_value
    if "=" in cleaned:
        _, assignment_value = cleaned.split("=", 1)
        return assignment_value
    return cleaned


def _shell_token_path_candidates(token: str) -> list[str]:
    cleaned = _shell_option_value(token.strip("\"'"))
    if not cleaned or any(char.isspace() for char in cleaned):
        return []
    if _is_shell_glob_token(cleaned):
        return []
    matches = [match.group(0) for match in _SHELL_PATHISH_PATTERN.finditer(cleaned)]
    if matches:
        return matches
    lower_cleaned = cleaned.lower()
    if (
        "/" in token
        or "\\" in token
        or token.startswith(("~", "./", "../"))
        or cleaned[:1].isupper()
        or lower_cleaned in _SHELL_KNOWN_FILENAMES
    ):
        return [cleaned]
    return []


def _powershell_candidate_paths(command: str) -> list[str]:
    seen: list[str] = []
    path_value = r"(?P<quote>['\"]?)(?P<path>[^'\"\s;|]+)(?P=quote)"
    parameter_pattern = re.compile(
        rf"(?i)(?:^|\s)-(?:literalpath|path|filepath|destination|outfilepath|outfile)\s+{path_value}"
    )
    cmdlet_pattern = re.compile(
        rf"(?i)\b(?:set-content|add-content|out-file|remove-item|copy-item|move-item|new-item|get-content|test-path)\b\s+{path_value}"
    )
    windows_path_pattern = re.compile(
        r"(?:[A-Za-z]:[\\/][^\s;|&]+|\.{1,2}[\\/][^\s;|&]+|[A-Za-z0-9_.-]+[\\/][^\s;|&]+\.[A-Za-z0-9]+)"
    )
    redirection_pattern = re.compile(r"(?:\*|\d+)?>>?\s*([^\s;|&]+)")
    for pattern in (parameter_pattern, cmdlet_pattern):
        for match in pattern.finditer(command):
            _append_unique_shell_path(seen, match.group("path"))
    for match in windows_path_pattern.finditer(command):
        _append_unique_shell_path(seen, match.group(0))
    for match in redirection_pattern.finditer(command):
        _append_unique_shell_path(seen, match.group(1))
    return seen


def _shell_redirection_paths(command: str) -> list[str]:
    paths: list[str] = []
    for match in _SHELL_REDIRECTION_PATTERN.finditer(command):
        redirection_target = match.group(1).strip("\"'")
        if redirection_target != "/dev/null":
            paths.append(redirection_target)
    return paths


def shell_command_paths(command: str, shell_kind: str | None = None) -> list[str]:
    seen = _powershell_candidate_paths(command) if shell_kind == "powershell" else []
    tokens = _shell_tokens(command)
    executable_indexes = _shell_command_executable_indexes(tokens)

    for index, token in enumerate(tokens):
        if index in executable_indexes:
            continue
        for path_value in _shell_token_path_candidates(token):
            _append_unique_shell_path(seen, path_value)
    for path_value in _shell_redirection_paths(command):
        _append_unique_shell_path(seen, path_value)
    return seen
