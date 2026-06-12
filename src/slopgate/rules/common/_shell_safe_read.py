"""Shell command read-safety helpers."""

from __future__ import annotations

import re
import shlex

from slopgate.constants import SAFE_READ_SHELL_VERBS

FIND_MUTATING_ACTIONS = frozenset({"-delete", "-exec", "-execdir", "-ok", "-okdir"})
_SHELL_REDIRECT_RE = re.compile(r"(?:[12]?>>?|&>)\s*([^\s;&|]+)")
_ALLOWED_REDIRECT_TARGETS = frozenset({"/dev/null", "nul", "&1", "&2"})


def command_has_word(command: str, word: str) -> bool:
    """Check if *word* appears as a standalone token in *command*."""
    escaped = re.escape(word)
    pattern = rf"(^|\s){escaped}(\s|$)"
    return bool(re.search(pattern, command, re.IGNORECASE))


def shell_tokens(command: str) -> list[str]:
    try:
        return shlex.split(command, posix=True)
    except ValueError:
        return command.split()


def find_command_has_mutation(tokens: list[str]) -> bool:
    return "find" in tokens and bool(FIND_MUTATING_ACTIONS & set(tokens))


def _has_unsafe_shell_redirection(command: str) -> bool:
    """Return True when shell redirection writes somewhere other than a null/fd sink."""
    for match in _SHELL_REDIRECT_RE.finditer(command):
        target = match.group(1).strip("'\"").lower()
        if target not in _ALLOWED_REDIRECT_TARGETS:
            return True
    return False


def _is_readonly_sed_command(command: str) -> bool:
    """Return True for sed -n print-only inspection (not substitution transforms)."""
    lowered = command.lower()
    if not command_has_word(lowered, "sed"):
        return False
    if "sed -i" in lowered:
        return False
    if _has_unsafe_shell_redirection(lowered):
        return False
    return bool(re.search(r"(?:^|\s)-n(?:\s|$)", lowered))


def is_safe_read_shell_command(
    command: str, *, reject_find_mutation: bool = False
) -> bool:
    lowered = command.lower()
    if "sed -i" in lowered or "tee " in lowered:
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
    if _has_unsafe_shell_redirection(lowered):
        return False
    if reject_find_mutation and find_command_has_mutation(shell_tokens(lowered)):
        return False
    return (
        _is_readonly_sed_command(command)
        or any(command_has_word(lowered, verb) for verb in SAFE_READ_SHELL_VERBS)
        or any(
            command_has_word(lowered, verb)
            for verb in ("get-content", "select-string", "test-path")
        )
    )
