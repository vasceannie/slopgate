from __future__ import annotations

import re


ALLOWED_REDIRECT_TARGETS = frozenset({"/dev/null", "nul", "&1", "&2"})
_SHELL_REDIRECTION_PATTERN_TEXT = r"(?:\d*>>?|\d*<)\s*([^\s;|&]+)"
_SHELL_WRITE_REDIRECT_TEXT = r"(?:[12]?>>?|&>)\s*([^\s;&|]+)"
_SHELL_PATHISH_TEXT = (
    r"(?:[A-Za-z]:[\\/])?"
    r"(?:[~./\\A-Za-z0-9_-]+[/\\])*"
    r"[A-Za-z0-9_.-]+\.[A-Za-z0-9]+"
)
SHELL_WRITE_REDIRECT_RE = re.compile(_SHELL_WRITE_REDIRECT_TEXT)
_SHELL_REDIRECTION_PATTERN = re.compile(_SHELL_REDIRECTION_PATTERN_TEXT)
_SHELL_PATHISH_PATTERN = re.compile(_SHELL_PATHISH_TEXT)
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
_SCRIPT_KNOWN_FILENAME_TEXT = "|".join(sorted(_SHELL_KNOWN_FILENAMES))
SCRIPT_PATH_TEXT = (
    r"(?:(?:[^'\"\n;|&]+?\.[A-Za-z0-9]+)"
    rf"|(?:{_SCRIPT_KNOWN_FILENAME_TEXT}))"
)
_SHELL_TEXT_OPTION_NAMES = frozenset(
    {"--reason", "--message", "--description", "--comment", "--title"}
)


def _is_shell_glob_token(value: str) -> bool:
    """Return True when a shell token is a glob pattern, not a literal path."""
    return any(char in value for char in "*?[")


def append_unique_shell_path(seen: list[str], value: str) -> None:
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


def shell_token_path_candidates(token: str) -> list[str]:
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


def powershell_candidate_paths(command: str) -> list[str]:
    seen: list[str] = []
    path_value = r"(?P<quote>['\"]?)(?P<path>(?!-)[^'\"\s;|]+)(?P=quote)"
    parameter_names = "literalpath|path|filepath|destination|outfilepath|outfile"
    parameter_pattern = re.compile(
        rf"(?i)(?:^|\s)-(?:{parameter_names})\s+{path_value}"
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
            append_unique_shell_path(seen, match.group("path"))
    for match in windows_path_pattern.finditer(command):
        append_unique_shell_path(seen, match.group(0))
    for match in redirection_pattern.finditer(command):
        append_unique_shell_path(seen, match.group(1))
    return seen


def shell_redirection_paths(command: str) -> list[str]:
    paths: list[str] = []
    for match in _SHELL_REDIRECTION_PATTERN.finditer(command):
        redirection_target = match.group(1).strip("\"'")
        if redirection_target != "/dev/null":
            paths.append(redirection_target)
    return paths


def shell_write_redirection_paths(command: str) -> list[str]:
    paths: list[str] = []
    for match in SHELL_WRITE_REDIRECT_RE.finditer(command):
        target = match.group(1).strip("\"'")
        if target.lower() not in ALLOWED_REDIRECT_TARGETS:
            paths.append(target)
    return paths
