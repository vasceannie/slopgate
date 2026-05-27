"""Claude Code installer support."""

from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import cast

from vibeforcer._types import object_dict
from vibeforcer.constants import METADATA_COMMAND, POST_TOOL_USE, PRE_TOOL_USE
from vibeforcer.installer._shared import (
    HOOK_TYPE_COMMAND,
    find_binary,
    merge_owned_hooks_into,
    remove_owned_hooks,
    write_json_with_backup,
)

_CLAUDE_EVENTS = (
    "SessionStart",
    "CwdChanged",
    "UserPromptSubmit",
    PRE_TOOL_USE,
    "PermissionRequest",
    POST_TOOL_USE,
    "PostToolUseFailure",
    "Stop",
    "SubagentStop",
    "TaskCompleted",
    "TeammateIdle",
    "InstructionsLoaded",
    "ConfigChange",
)

_ClaudeHookCommand = dict[str, str]
_ClaudeHookEntry = dict[str, str | list[_ClaudeHookCommand]]
_ClaudeHooks = dict[str, list[_ClaudeHookEntry]]


def _claude_hooks_block(binary: str) -> _ClaudeHooks:
    """Build the hooks block for Claude Code settings.json."""
    hooks: _ClaudeHooks = {}
    command = f"{shlex.quote(binary)} handle"
    for event in _CLAUDE_EVENTS:
        command_entry: _ClaudeHookCommand = {
            "type": HOOK_TYPE_COMMAND,
            METADATA_COMMAND: command,
        }
        entry: _ClaudeHookEntry = {"hooks": [command_entry]}
        if event == "SessionStart":
            entry["matcher"] = "startup|resume"
        hooks[event] = [entry]
    return hooks


def _install_claude(dry_run: bool = False) -> int:
    binary = find_binary()
    settings_path = Path.home() / ".claude" / "settings.json"
    hooks = _claude_hooks_block(binary)

    if dry_run:
        print(f"Would patch: {settings_path}")
        print(f"Binary: {binary}")
        print(json.dumps({"hooks": hooks}, indent=2))
        return 0

    if settings_path.exists():
        try:
            parsed = cast(object, json.loads(settings_path.read_text(encoding="utf-8")))
            settings = object_dict(parsed)
        except json.JSONDecodeError:
            print(f"Invalid Claude settings JSON; refusing to overwrite: {settings_path}")
            return 1
    else:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings = {}

    merge_owned_hooks_into(settings, cast(dict[str, list[dict[str, object]]], hooks))
    write_json_with_backup(settings_path, settings, "settings")
    print(f"Installed vibeforcer hooks into {settings_path}")
    print(f"Binary: {binary}")
    print(f"Events: {len(_CLAUDE_EVENTS)}")
    return 0


def _uninstall_claude(dry_run: bool = False) -> int:
    settings_path = Path.home() / ".claude" / "settings.json"
    if not settings_path.exists():
        print("No Claude settings found.")
        return 0

    try:
        parsed = cast(object, json.loads(settings_path.read_text(encoding="utf-8")))
    except json.JSONDecodeError:
        print(f"Invalid Claude settings JSON; refusing to modify: {settings_path}")
        return 1
    settings = object_dict(parsed)
    if "hooks" not in settings:
        print("No hooks found in Claude settings.")
        return 0

    if dry_run:
        print(f"Would remove vibeforcer hook entries from {settings_path}")
        return 0

    remaining_hooks = remove_owned_hooks(settings.get("hooks"))
    if remaining_hooks:
        settings["hooks"] = remaining_hooks
    else:
        del settings["hooks"]
    write_json_with_backup(settings_path, settings, "settings")
    print(f"Removed vibeforcer hooks from {settings_path}")
    return 0
