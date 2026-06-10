"""Claude Code installer support."""

from __future__ import annotations
import json
from pathlib import Path
from typing import cast
from slopgate.constants import METADATA_COMMAND, POST_TOOL_USE, PRE_TOOL_USE
from slopgate.installer._install_scope import (
    ResidualInstallScopeWarning,
    json_has_owned_slopgate_hooks,
    normalize_install_scope,
    resolve_project_root,
    scope_paths,
    warn_residual_install_scope,
)
import slopgate.installer._shared
from slopgate.installer._shared import (
    HOOK_TYPE_COMMAND,
    hook_command,
    merge_owned_hooks_into,
    remove_owned_hooks,
    require_json_object,
    write_json_with_backup,
)

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
_ClaudeHookCommand = dict[str, str]
_ClaudeHookEntry = dict[str, str | list[_ClaudeHookCommand]]
_ClaudeHooks = dict[str, list[_ClaudeHookEntry]]


def _claude_user_settings_path() -> Path:
    return Path.home() / ".claude" / "settings.json"


def _claude_project_settings_path(project_root: Path) -> Path:
    return project_root / ".claude" / "settings.json"


def claude_hooks_block(binary: str) -> _ClaudeHooks:
    """Build the hooks block for Claude Code settings.json."""
    hooks: _ClaudeHooks = {}
    command = hook_command(binary, "handle")
    for event in CLAUDE_EVENTS:
        command_entry: _ClaudeHookCommand = {
            "type": HOOK_TYPE_COMMAND,
            METADATA_COMMAND: command,
        }
        entry: _ClaudeHookEntry = {"hooks": [command_entry]}
        if event == "SessionStart":
            entry["matcher"] = "startup|resume"
        hooks[event] = [entry]
    return hooks


def _write_claude_settings(
    settings_path: Path, settings: dict[str, object], status_line: str
) -> int:
    write_json_with_backup(settings_path, settings, "settings")
    print(status_line)
    return 0


def _install_claude_at(
    settings_path: Path, hooks: _ClaudeHooks, *, dry_run: bool
) -> int:
    if dry_run:
        print(f"Would patch: {settings_path}")
        print(json.dumps({"hooks": hooks}, indent=2))
        return 0
    if not settings_path.exists():
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings = {}
    elif (
        settings := require_json_object(
            settings_path, "Claude settings", action="overwrite"
        )
    ) is None:
        return 1
    merge_owned_hooks_into(settings, cast(dict[str, list[dict[str, object]]], hooks))
    return _write_claude_settings(
        settings_path, settings, f"Installed slopgate hooks into {settings_path}"
    )


def install_claude(
    dry_run: bool = False, *, scope: str = "user", project_root: Path | None = None
) -> int:
    install_scope = normalize_install_scope(scope)
    binary = slopgate.installer._shared.find_binary()
    hooks = claude_hooks_block(binary)
    root = resolve_project_root(project_root)
    paths = scope_paths(
        install_scope,
        user_path=_claude_user_settings_path(),
        project_path=_claude_project_settings_path(root),
    )
    if dry_run:
        print(f"Binary: {binary}")
        print(f"Events: {len(CLAUDE_EVENTS)}")
    completed: list[Path] = []
    last_status = 0
    for settings_path in paths:
        status = _install_claude_at(settings_path, hooks, dry_run=dry_run)
        if status != 0:
            if not dry_run:
                for rollback_path in completed:
                    _ = _uninstall_claude_at(rollback_path, dry_run=False)
            return status
        completed.append(settings_path)
        last_status = status
    if not dry_run and last_status == 0:
        print(f"Binary: {binary}")
        print(f"Events: {len(CLAUDE_EVENTS)}")
    return last_status


def _uninstall_claude_at(settings_path: Path, *, dry_run: bool) -> int:
    if not settings_path.exists():
        return 0
    settings = require_json_object(settings_path, "Claude settings", action="modify")
    if settings is None:
        return 1
    if "hooks" not in settings:
        return 0
    if dry_run:
        print(f"Would remove slopgate hook entries from {settings_path}")
        return 0
    remaining_hooks = remove_owned_hooks(settings.get("hooks"))
    if remaining_hooks:
        settings["hooks"] = remaining_hooks
    else:
        del settings["hooks"]
    return _write_claude_settings(
        settings_path, settings, f"Removed slopgate hooks from {settings_path}"
    )


def uninstall_claude(
    dry_run: bool = False, *, scope: str = "user", project_root: Path | None = None
) -> int:
    install_scope = normalize_install_scope(scope)
    root = resolve_project_root(project_root)
    paths = scope_paths(
        install_scope,
        user_path=_claude_user_settings_path(),
        project_path=_claude_project_settings_path(root),
    )
    any_found = False
    last_status = 0
    for settings_path in paths:
        if settings_path.exists():
            any_found = True
        status = _uninstall_claude_at(settings_path, dry_run=dry_run)
        if status != 0:
            return status
        last_status = status
    if not any_found and install_scope == "user":
        print("No Claude settings found.")
    if not dry_run:
        warn_residual_install_scope(
            ResidualInstallScopeWarning(
                platform_label="Claude",
                scope=scope,
                user_path=_claude_user_settings_path(),
                project_path=_claude_project_settings_path(root),
                project_root=project_root,
                has_owned=json_has_owned_slopgate_hooks,
            )
        )
    return last_status
