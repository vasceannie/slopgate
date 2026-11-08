"""Dry-run and hook command text, rendered the way the installer renders it."""

from __future__ import annotations

from slopgate.installer._shared import shell_command
from slopgate.util.platform import is_windows

__all__ = ["unquoted_command", "would_run_prefix"]

_WINDOWS_SCRIPT_QUOTE = 1


def would_run_prefix(*argv: str) -> str:
    """Return the text a dry-run line starts with for a command beginning ``argv``.

    On Windows the installer wraps the whole argv in one quoted PowerShell script, so
    the closing quote is dropped to let a command with further arguments match.
    """
    command = shell_command(list(argv))
    if is_windows():
        command = command[:-_WINDOWS_SCRIPT_QUOTE]
    return f"Would run: {command}"


def unquoted_command(command: str) -> str:
    """Return a rendered hook command with PowerShell's per-argument quoting removed.

    Windows hook commands quote each argument (``'--platform' 'claude'``); stripping the
    quotes lets one substring assertion cover both renderings.
    """
    return command.replace("'", "") if is_windows() else command
