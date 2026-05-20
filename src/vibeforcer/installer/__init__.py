"""Platform installer — patches settings files to wire vibeforcer hooks.

Supports:
  vibeforcer install claude    → patches ~/.claude/settings.json
  vibeforcer install codex     → patches ~/.codex/hooks.json
  vibeforcer install opencode  → copies TS plugin to ~/.config/opencode/plugins/
"""

from __future__ import annotations

from vibeforcer.installer import _claude, _codex, _opencode
from vibeforcer.installer._claude import _CLAUDE_EVENTS, _claude_hooks_block
from vibeforcer.installer._codex import (
    _CODEX_EVENTS,
    _codex_hooks_block,
    _enable_codex_hooks_toml,
)
from vibeforcer.installer._shared import find_binary as _find_binary


def _install_claude(dry_run: bool = False) -> int:
    _claude.find_binary = _find_binary
    return _claude._install_claude(dry_run=dry_run)


_uninstall_claude = _claude._uninstall_claude


def _install_codex(dry_run: bool = False) -> int:
    _codex.find_binary = _find_binary
    return _codex._install_codex(dry_run=dry_run)


_uninstall_codex = _codex._uninstall_codex


def _install_opencode(dry_run: bool = False) -> int:
    _opencode.find_binary = _find_binary
    return _opencode._install_opencode(dry_run=dry_run)


_uninstall_opencode = _opencode._uninstall_opencode


_INSTALLERS = {
    "claude": (_install_claude, _uninstall_claude),
    "codex": (_install_codex, _uninstall_codex),
    "opencode": (_install_opencode, _uninstall_opencode),
}


def install_platform(platform: str, dry_run: bool = False) -> int:
    installer, _ = _INSTALLERS[platform]
    return installer(dry_run=dry_run)


def uninstall_platform(platform: str, dry_run: bool = False) -> int:
    _, uninstaller = _INSTALLERS[platform]
    return uninstaller(dry_run=dry_run)


__all__ = [
    "_CLAUDE_EVENTS",
    "_CODEX_EVENTS",
    "_claude_hooks_block",
    "_codex_hooks_block",
    "_enable_codex_hooks_toml",
    "_find_binary",
    "_install_claude",
    "_install_codex",
    "_install_opencode",
    "_uninstall_claude",
    "_uninstall_codex",
    "_uninstall_opencode",
    "install_platform",
    "uninstall_platform",
]
