"""Claude Code native-plugin installer support."""

from __future__ import annotations

import json
import os
from dataclasses import replace
from functools import cache, partial
from pathlib import Path

from slopgate.constants import (
    METADATA_COMMAND,
    PLATFORM_CLAUDE,
    POST_TOOL_USE,
    PRE_TOOL_USE,
    WSL_DISTRO_ENV,
    WSL_USER_ENV,
)
from slopgate.installer._shared import HOOK_TYPE_COMMAND, hook_command
from slopgate.installer.native.claude import (
    CLAUDE_EXECUTABLE,
    CLAUDE_PLUGIN_DESCRIPTION,
    CLAUDE_PLUGIN_NAME,
    ClaudeHost,
    ClaudeLayout,
)
from slopgate.installer.native.marketplace import (
    install_marketplace_host,
    uninstall_marketplace_host,
)
from slopgate.installer.native.entry import run_native_install

from slopgate.installer.native.model import (
    HOOKS_KEY,
    VERSION_KEY,
    make_request_or_report,
)
from slopgate.installer.native.paths import (
    project_host_file,
    user_host_root,
)
from slopgate.installer.native.wsl import WslPaths, wsl_paths_for

__all__ = ["install_claude", "uninstall_claude"]

CLAUDE_EVENTS = (
    "SessionStart",
    "CwdChanged",
    "UserPromptSubmit",
    PRE_TOOL_USE,
    "PermissionRequest",
    POST_TOOL_USE,
    "PostToolUseFailure",
    "Stop",
    "SubagentStart",
    "SubagentStop",
    "TaskCompleted",
    "TeammateIdle",
    "InstructionsLoaded",
    "ConfigChange",
)
_PLUGIN_MANIFEST = ".claude-plugin/plugin.json"
_PLUGIN_HOOKS = "hooks/hooks.json"
_ClaudeHookCommand = dict[str, str]
_ClaudeHookEntry = dict[str, str | list[_ClaudeHookCommand]]
_ClaudeHooks = dict[str, list[_ClaudeHookEntry]]
# Prepended for a Claude that runs inside WSL: its POSIX shell runs the hook,
# and WSLENV hands the distribution name and the hook's own user to the
# Windows Slopgate, so Linux payload paths resolve in the distribution, and
# with the permissions, of the session that sent them.
_WSL_ORIGIN_FORWARD = (
    f'{WSL_USER_ENV}="$(id -un)" '
    f'WSLENV="{WSL_DISTRO_ENV}:{WSL_USER_ENV}${{WSLENV:+:$WSLENV}}" '
)


def claude_hooks_block(binary: str, *, wsl_hosted: bool = False) -> _ClaudeHooks:
    """Build the hook definitions used by the Claude enforcement plugin."""
    hooks: _ClaudeHooks = {}
    command = hook_command(binary, "handle", "--platform", PLATFORM_CLAUDE)
    if wsl_hosted:
        command = _WSL_ORIGIN_FORWARD + command
    for event in CLAUDE_EVENTS:
        command_entry: _ClaudeHookCommand = {
            "type": HOOK_TYPE_COMMAND,
            METADATA_COMMAND: command,
        }
        entry: _ClaudeHookEntry = {HOOKS_KEY: [command_entry]}
        if event == "SessionStart":
            entry["matcher"] = "startup|resume|clear|compact|fork"
        hooks[event] = [entry]
    return hooks


def _render_payload(
    binary: str, version: str, *, wsl_hosted: bool = False
) -> dict[str, str]:
    manifest = {
        "name": CLAUDE_PLUGIN_NAME,
        VERSION_KEY: version,
        "description": CLAUDE_PLUGIN_DESCRIPTION,
    }
    hooks = {HOOKS_KEY: claude_hooks_block(binary, wsl_hosted=wsl_hosted)}
    return {
        _PLUGIN_MANIFEST: json.dumps(manifest, indent=2) + "\n",
        _PLUGIN_HOOKS: json.dumps(hooks, indent=2) + "\n",
    }


_SETTINGS_FILE = "settings.json"


def _claude_user_root() -> Path:
    override = os.environ.get("CLAUDE_CONFIG_DIR")
    if override:
        return Path(override).expanduser()
    return user_host_root(PLATFORM_CLAUDE)


def _claude_user_settings() -> Path:
    return _claude_user_root() / _SETTINGS_FILE


_LAYOUT = ClaudeLayout(
    user_settings=_claude_user_settings,
    project_settings=partial(project_host_file, PLATFORM_CLAUDE, _SETTINGS_FILE),
    user_root=_claude_user_root,
    render_payload=_render_payload,
)


def _wsl_layout(wsl: WslPaths) -> ClaudeLayout:
    """The layout whose user settings live in the WSL home, opened from Windows."""
    user_root = cache(wsl.claude_config_dir)
    return replace(
        _LAYOUT,
        user_root=user_root,
        user_settings=lambda: user_root() / _SETTINGS_FILE,
        render_payload=partial(_render_payload, wsl_hosted=True),
    )


def _claude_host() -> ClaudeHost:
    """The Claude host, bridged to WSL when ``claude`` is a WSL-forwarding shim."""
    wsl = wsl_paths_for(CLAUDE_EXECUTABLE, Path.cwd())
    if wsl is None:
        return ClaudeHost(_LAYOUT)
    return ClaudeHost(_wsl_layout(wsl), wsl)


def install_claude(
    dry_run: bool = False, *, scope: str = "user", project_root: Path | None = None
) -> int:
    return run_native_install(
        scope,
        project_root,
        dry_run,
        partial(install_marketplace_host, _claude_host()),
    )


def uninstall_claude(
    dry_run: bool = False, *, scope: str = "user", project_root: Path | None = None
) -> int:
    request = make_request_or_report(scope, project_root, dry_run)
    if request is None:
        return 1
    return uninstall_marketplace_host(_claude_host(), request)
