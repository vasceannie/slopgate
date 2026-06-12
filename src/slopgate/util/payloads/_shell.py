from __future__ import annotations

import re
import shlex
from pathlib import Path

from ._shell_paths import (
    ALLOWED_REDIRECT_TARGETS,
    SHELL_WRITE_REDIRECT_RE,
    append_unique_shell_path,
    powershell_candidate_paths,
    shell_redirection_paths,
    shell_token_path_candidates,
)
from ._shell_script_writes import script_api_write_paths


_COMMAND_SEPARATORS = frozenset({"&&", "||", ";", "|"})
_COMMAND_WRAPPER_NAMES = frozenset(
    {"env", "command", "builtin", "exec", "time", "nohup"}
)
FIND_MUTATING_ACTIONS = frozenset({"-delete", "-exec", "-execdir", "-ok", "-okdir"})
_MUTATING_SHELL_VERBS = frozenset(
    {
        "chmod",
        "chown",
        "cp",
        "install",
        "mkdir",
        "mv",
        "rm",
        "rmdir",
        "tee",
        "touch",
        "truncate",
    }
)
_INTERPRETER_SHELL_VERBS = frozenset(
    {"awk", "node", "nodejs", "perl", "python", "python3", "ruby"}
)
_READ_ONLY_SHELL_VERBS = frozenset(
    {
        "cat",
        "file",
        "find",
        "grep",
        "head",
        "jq",
        "ls",
        "nl",
        "rg",
        "sed",
        "stat",
        "tail",
        "wc",
    }
)
_RTK_SAFE_READ_SUBCOMMANDS = frozenset(
    {
        "cat",
        "file",
        "find",
        "grep",
        "head",
        "jq",
        "ls",
        "nl",
        "read",
        "rg",
        "sed",
        "stat",
        "tail",
        "wc",
    }
)
_EMBEDDED_COMMAND_RE = re.compile(
    r"\b(?:system|popen|run|call|check_call|check_output)\(\s*['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
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


def _shell_script_argument_indexes(
    tokens: list[str], executable_indexes: set[int]
) -> set[int]:
    """Return indexes for interpreter inline script bodies, not file targets."""
    script_indexes: set[int] = set()
    for executable_index in executable_indexes:
        executable_name = Path(tokens[executable_index].strip("\"'")).name.lower()
        if executable_name not in _INTERPRETER_SHELL_VERBS:
            continue
        for index in range(executable_index + 1, len(tokens)):
            cleaned = tokens[index].strip("\"'")
            if cleaned in _COMMAND_SEPARATORS:
                break
            if cleaned in {"-c", "-e"} and index + 1 < len(tokens):
                script_indexes.add(index + 1)
    return script_indexes


def shell_command_executable_paths(command: str) -> list[str]:
    """Return path-like executable tokens that appear in command position."""
    tokens = shell_tokens(command)
    executable_indexes = _shell_command_executable_indexes(tokens)
    return [tokens[index].strip("\"'") for index in sorted(executable_indexes)]


def shell_tokens(command: str) -> list[str]:
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        return command.split()


def command_has_word(command: str, word: str) -> bool:
    """Check if *word* appears as a standalone token in *command*."""
    escaped = re.escape(word)
    pattern = rf"(^|\s){escaped}(\s|$)"
    return bool(re.search(pattern, command, re.IGNORECASE))


def find_command_has_mutation(tokens: list[str]) -> bool:
    command_names = {Path(token.strip("\"'")).name for token in tokens}
    return "find" in command_names and bool(FIND_MUTATING_ACTIONS & set(tokens))


def _has_unsafe_shell_redirection(command: str) -> bool:
    """Return True when shell redirection writes somewhere other than a null/fd sink."""
    for match in SHELL_WRITE_REDIRECT_RE.finditer(command):
        target = match.group(1).strip("'\"").lower()
        if target not in ALLOWED_REDIRECT_TARGETS:
            return True
    return False


def _is_readonly_sed_command(command: str) -> bool:
    """Return True for sed -n print-only inspection, not in-place transforms."""
    lowered = command.lower()
    if not command_has_word(lowered, "sed"):
        return False
    if "sed -i" in lowered:
        return False
    if _has_unsafe_shell_redirection(lowered):
        return False
    return bool(re.search(r"(?:^|\s)-n(?:\s|$)", lowered))


def _rtk_subcommand(tokens: list[str], executable_index: int) -> str:
    for token in tokens[executable_index + 1 :]:
        cleaned = token.strip("\"'").lower()
        if cleaned in _COMMAND_SEPARATORS:
            return ""
        if cleaned.startswith("-"):
            continue
        return Path(cleaned).name
    return ""


def _safe_read_executable_names(command: str) -> list[str]:
    tokens = shell_tokens(command)
    indexes = _shell_command_executable_indexes(tokens)
    names: list[str] = []
    for index in sorted(indexes):
        name = Path(tokens[index].strip("\"'")).name.lower()
        if name == "rtk":
            names.append(_rtk_subcommand(tokens, index))
            continue
        names.append(name)
    return names


def _has_mutating_shell_verb(command: str) -> bool:
    tokens = shell_tokens(command.lower())
    indexes = _shell_command_executable_indexes(tokens)
    return any(Path(tokens[index]).name in _MUTATING_SHELL_VERBS for index in indexes)


def _has_interpreter_write_snippet(command: str) -> bool:
    lowered = command.lower()
    tokens = shell_tokens(lowered)
    indexes = _shell_command_executable_indexes(tokens)
    if not any(Path(tokens[index]).name in _INTERPRETER_SHELL_VERBS for index in indexes):
        return False
    if script_write_paths(command):
        return True
    if _has_embedded_mutating_shell(command):
        return True
    return any(
        marker in lowered
        for marker in (
            ".write(",
            ".writelines(",
            ".truncate(",
            "fs.writefile",
            "fs.appendfile",
            "deno.write",
            "file.write",
            "os.write(",
            ".write_text(",
            ".write_bytes(",
            "path.write_text",
            "path.write_bytes",
            "writefile",
        )
    )


def _has_embedded_mutating_shell(command: str) -> bool:
    for match in _EMBEDDED_COMMAND_RE.finditer(command):
        embedded = match.group(1)
        lowered = embedded.lower()
        if _has_unsafe_shell_redirection(lowered):
            return True
        if find_command_has_mutation(shell_tokens(lowered)):
            return True
        if _has_mutating_shell_verb(lowered):
            return True
    return False


def is_mutating_shell_command(command: str) -> bool:
    lowered = command.lower()
    if "sed -i" in lowered or "tee " in lowered:
        return True
    if _has_unsafe_shell_redirection(lowered):
        return True
    if find_command_has_mutation(shell_tokens(lowered)):
        return True
    if _has_interpreter_write_snippet(lowered):
        return True
    return _has_mutating_shell_verb(lowered)


def is_safe_read_shell_command(
    command: str, *, reject_find_mutation: bool = False
) -> bool:
    lowered = command.lower()
    if is_mutating_shell_command(lowered):
        return False
    if any(
        token in lowered
        for token in (
            "set-content",
            "add-content",
            "out-file",
            "remove-item",
            "copy-item",
            "move-item",
            "new-item",
        )
    ):
        return False
    if reject_find_mutation and find_command_has_mutation(shell_tokens(lowered)):
        return False
    names = _safe_read_executable_names(command)
    if not names:
        return False
    for name in names:
        if name == "sed" and not _is_readonly_sed_command(command):
            return False
        if name not in _READ_ONLY_SHELL_VERBS and name not in _RTK_SAFE_READ_SUBCOMMANDS:
            return False
    return True


def script_write_paths(command: str) -> list[str]:
    seen = script_api_write_paths(command)
    for match in _EMBEDDED_COMMAND_RE.finditer(command):
        embedded = match.group(1)
        if not is_mutating_shell_command(embedded):
            continue
        for path_value in shell_command_paths(embedded):
            append_unique_shell_path(seen, path_value)
    return seen


def shell_command_paths(command: str, shell_kind: str | None = None) -> list[str]:
    seen = powershell_candidate_paths(command) if shell_kind == "powershell" else []
    tokens = shell_tokens(command)
    executable_indexes = _shell_command_executable_indexes(tokens)
    script_argument_indexes = _shell_script_argument_indexes(tokens, executable_indexes)

    for index, token in enumerate(tokens):
        if index in executable_indexes or index in script_argument_indexes:
            continue
        for path_value in shell_token_path_candidates(token):
            append_unique_shell_path(seen, path_value)
    for path_value in shell_redirection_paths(command):
        append_unique_shell_path(seen, path_value)
    for path_value in script_write_paths(command):
        append_unique_shell_path(seen, path_value)
    return seen
