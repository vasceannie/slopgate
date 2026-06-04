"""Platform installer — patches settings files to wire slopgate hooks.

Supports:
  slopgate install claude    → ~/.claude/settings.json and/or .claude/settings.json
  slopgate install codex     → ~/.codex/hooks.json and/or .codex/hooks.json
  slopgate install opencode  → user plugin dir and/or .opencode/plugins/
  slopgate install cursor    → ~/.cursor/hooks.json and/or .cursor/hooks.json

Use --install-scope {user,project,both} (alias: --cursor-scope) on install/uninstall.
"""

from __future__ import annotations

from pathlib import Path

from slopgate.installer import _claude, _codex, _cursor, _opencode, _suite
from slopgate.installer._claude import _CLAUDE_EVENTS, _claude_hooks_block
from slopgate.installer._codex import (
    _CODEX_EVENTS,
    _codex_hooks_block,
    _enable_codex_hooks_toml,
)
from slopgate.installer._cursor import (
    CURSOR_INSTALL_SCOPES,
    _CURSOR_EVENTS,
    _cursor_hooks_block,
    _cursor_project_hooks_path,
)
from slopgate.installer._install_scope import INSTALL_SCOPES
from slopgate.installer._shared import find_binary as _find_binary

_install_claude = _claude._install_claude
_uninstall_claude = _claude._uninstall_claude
_install_codex = _codex._install_codex
_uninstall_codex = _codex._uninstall_codex
_install_opencode = _opencode._install_opencode
_uninstall_opencode = _opencode._uninstall_opencode
_install_cursor = _cursor._install_cursor
_uninstall_cursor = _cursor._uninstall_cursor

install_suite = _suite.install_suite
SuiteInstallOptions = _suite.SuiteInstallOptions
SuiteUninstallOptions = _suite.SuiteUninstallOptions
SuiteUpdateOptions = _suite.SuiteUpdateOptions
uninstall_autoupdate = _suite.uninstall_autoupdate
uninstall_suite = _suite.uninstall_suite
update_suite = _suite.update_suite

_INSTALLERS = {
    "claude": (_claude._install_claude, _claude._uninstall_claude),
    "codex": (_codex._install_codex, _codex._uninstall_codex),
    "cursor": (_cursor._install_cursor, _cursor._uninstall_cursor),
    "opencode": (_opencode._install_opencode, _opencode._uninstall_opencode),
}


def _resolved_project_root(project_root: Path | None) -> Path | None:
    if project_root is None:
        return None
    return project_root.expanduser().resolve()


def install_platform(
    platform: str,
    dry_run: bool = False,
    *,
    install_scope: str = "user",
    project_root: Path | None = None,
) -> int:
    try:
        installer, _ = _INSTALLERS[platform]
        return installer(
            dry_run=dry_run,
            scope=install_scope,
            project_root=_resolved_project_root(project_root),
        )
    except ValueError as exc:
        print(exc)
        return 1


def uninstall_platform(
    platform: str,
    dry_run: bool = False,
    *,
    install_scope: str = "user",
    project_root: Path | None = None,
) -> int:
    try:
        _, uninstaller = _INSTALLERS[platform]
        return uninstaller(
            dry_run=dry_run,
            scope=install_scope,
            project_root=_resolved_project_root(project_root),
        )
    except ValueError as exc:
        print(exc)
        return 1


__all__ = [
    "_CLAUDE_EVENTS",
    "_CODEX_EVENTS",
    "CURSOR_INSTALL_SCOPES",
    "INSTALL_SCOPES",
    "_CURSOR_EVENTS",
    "_cursor_project_hooks_path",
    "_claude_hooks_block",
    "_codex_hooks_block",
    "_cursor_hooks_block",
    "_enable_codex_hooks_toml",
    "_find_binary",
    "_install_claude",
    "_install_codex",
    "_install_cursor",
    "_install_opencode",
    "_uninstall_claude",
    "_uninstall_codex",
    "_uninstall_cursor",
    "_uninstall_opencode",
    "install_platform",
    "install_suite",
    "SuiteInstallOptions",
    "SuiteUninstallOptions",
    "SuiteUpdateOptions",
    "uninstall_autoupdate",
    "uninstall_platform",
    "uninstall_suite",
    "update_suite",
]
