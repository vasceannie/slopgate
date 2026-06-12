"""Platform installer — patches settings files to wire slopgate hooks.

Supports:
  slopgate install claude    → ~/.claude/settings.json and/or .claude/settings.json
  slopgate install codex     → ~/.codex/hooks.json and/or .codex/hooks.json
  slopgate install opencode  → user plugin dir and/or .opencode/plugins/
  slopgate install cursor    → ~/.cursor/hooks.json and/or .cursor/hooks.json

Use --install-scope {user,project,both} (alias: --cursor-scope) on install/uninstall.
"""

from __future__ import annotations

__all__ = [
    "CLAUDE_EVENTS",
    "CODEX_EVENTS",
    "CURSOR_INSTALL_SCOPES",
    "INSTALL_SCOPES",
    "CURSOR_EVENTS",
    "cursor_project_hooks_path",
    "claude_hooks_block",
    "codex_hooks_block",
    "cursor_hooks_block",
    "enable_codex_hooks_toml",
    "install_claude",
    "install_codex",
    "install_cursor",
    "install_opencode",
    "uninstall_claude",
    "uninstall_codex",
    "uninstall_cursor",
    "uninstall_opencode",
    "install_platform",
    "install_suite",
    "SuiteInstallOptions",
    "SuiteUninstallOptions",
    "SuiteUpdateOptions",
    "uninstall_autoupdate",
    "uninstall_platform",
    "uninstall_suite",
    "update_suite",
    "Path",
    "_claude",
    "_codex",
    "_cursor",
    "_opencode",
    "_suite",
    "find_binary",
    "filter_owned_hook_commands",
    "merge_owned_hooks",
    "remove_owned_hooks",
    "_INSTALLERS",
]
from pathlib import Path
from slopgate.installer import _claude, _codex, _cursor, _opencode, _suite
from slopgate.installer._claude import CLAUDE_EVENTS, claude_hooks_block
from slopgate.installer._codex import (
    CODEX_EVENTS,
    codex_hooks_block,
    enable_codex_hooks_toml,
)
from slopgate.installer._cursor import (
    CURSOR_INSTALL_SCOPES,
    CURSOR_EVENTS,
    cursor_hooks_block,
    cursor_project_hooks_path,
)
from slopgate.installer._install_scope import INSTALL_SCOPES
from slopgate.installer._shared import (
    filter_owned_hook_commands,
    find_binary,
    merge_owned_hooks,
    remove_owned_hooks,
)

install_claude = _claude.install_claude
uninstall_claude = _claude.uninstall_claude
install_codex = _codex.install_codex
uninstall_codex = _codex.uninstall_codex
install_opencode = _opencode.install_opencode
uninstall_opencode = _opencode.uninstall_opencode
install_cursor = _cursor.install_cursor
uninstall_cursor = _cursor.uninstall_cursor
install_suite = _suite.install_suite
SuiteInstallOptions = _suite.SuiteInstallOptions
SuiteUninstallOptions = _suite.SuiteUninstallOptions
SuiteUpdateOptions = _suite.SuiteUpdateOptions
uninstall_autoupdate = _suite.uninstall_autoupdate
uninstall_suite = _suite.uninstall_suite
update_suite = _suite.update_suite
_INSTALLERS = {
    "claude": (_claude.install_claude, _claude.uninstall_claude),
    "codex": (_codex.install_codex, _codex.uninstall_codex),
    "cursor": (_cursor.install_cursor, _cursor.uninstall_cursor),
    "opencode": (_opencode.install_opencode, _opencode.uninstall_opencode),
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
