"""Cursor native hooks installer support."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from vibeforcer.installer._shared import (
    HOOK_TIMEOUT_LONG,
    HOOK_TIMEOUT_SHORT,
    HOOK_TIMEOUT_STANDARD,
    command_is_vibeforcer_hook,
    find_binary,
    hook_command,
    print_binary_install_summary,
    require_json_object,
    uninstall_hooks_file,
    write_json_with_backup,
)

_CursorHookEntry = dict[str, object]
_CursorHooks = dict[str, list[_CursorHookEntry]]

_CURSOR_EVENTS: dict[str, dict[str, object]] = {
    "preToolUse": {"timeout": HOOK_TIMEOUT_STANDARD, "failClosed": True},
    "postToolUse": {"timeout": HOOK_TIMEOUT_STANDARD, "failClosed": False},
    "postToolUseFailure": {"timeout": HOOK_TIMEOUT_SHORT, "failClosed": False},
    "beforeShellExecution": {"timeout": HOOK_TIMEOUT_STANDARD, "failClosed": True},
    "afterShellExecution": {"timeout": HOOK_TIMEOUT_STANDARD, "failClosed": False},
    "beforeReadFile": {"timeout": HOOK_TIMEOUT_SHORT, "failClosed": True},
    "afterFileEdit": {"timeout": HOOK_TIMEOUT_LONG, "failClosed": True},
    "beforeSubmitPrompt": {"timeout": HOOK_TIMEOUT_SHORT, "failClosed": False},
    "stop": {"timeout": HOOK_TIMEOUT_LONG, "failClosed": False},
    "subagentStart": {"timeout": HOOK_TIMEOUT_SHORT, "failClosed": False},
    "subagentStop": {"timeout": HOOK_TIMEOUT_STANDARD, "failClosed": False},
    "preCompact": {"timeout": HOOK_TIMEOUT_SHORT, "failClosed": False},
}


def _cursor_hooks_path() -> Path:
    return Path.home() / ".cursor" / "hooks.json"


def _cursor_hooks_block(binary: str) -> _CursorHooks:
    command = hook_command(binary, "handle", "--platform", "cursor")
    hooks: _CursorHooks = {}
    for event, meta in _CURSOR_EVENTS.items():
        entry: _CursorHookEntry = {"command": command}
        entry.update(meta)
        hooks[event] = [entry]
    return hooks


def _cursor_entry_is_owned(entry: object) -> bool:
    if not isinstance(entry, dict):
        return False
    command = cast(dict[object, object], entry).get("command")
    return command_is_vibeforcer_hook(command)


def _coerce_cursor_entries(value: object) -> list[_CursorHookEntry]:
    if not isinstance(value, list):
        return []
    entries: list[_CursorHookEntry] = []
    for item in value:
        if isinstance(item, dict) and all(isinstance(key, str) for key in item):
            entries.append(cast(_CursorHookEntry, dict(item)))
    return entries


def _merge_cursor_hooks(existing_hooks: object, managed_hooks: _CursorHooks) -> _CursorHooks:
    merged: _CursorHooks = {}
    if isinstance(existing_hooks, dict):
        for event, entries in cast(dict[object, object], existing_hooks).items():
            if isinstance(event, str):
                merged[event] = _coerce_cursor_entries(entries)
    for event, entries in managed_hooks.items():
        preserved = [entry for entry in merged.get(event, []) if not _cursor_entry_is_owned(entry)]
        merged[event] = [*preserved, *entries]
    return merged


def _remove_cursor_hooks(existing_hooks: object) -> _CursorHooks:
    remaining: _CursorHooks = {}
    if not isinstance(existing_hooks, dict):
        return remaining
    for event, entries in cast(dict[object, object], existing_hooks).items():
        if not isinstance(event, str):
            continue
        kept = [entry for entry in _coerce_cursor_entries(entries) if not _cursor_entry_is_owned(entry)]
        if kept:
            remaining[event] = kept
    return remaining


def _install_cursor(dry_run: bool = False) -> int:
    binary = find_binary()
    hooks_path = _cursor_hooks_path()
    hooks = _cursor_hooks_block(binary)

    if dry_run:
        print(f"Would write: {hooks_path}")
        print(f"Binary: {binary}")
        print(json.dumps({"version": 1, "hooks": hooks}, indent=2))
        return 0

    hooks_path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, object]
    if not hooks_path.exists():
        existing = {"version": 1}
    else:
        parsed = require_json_object(hooks_path, "Cursor hooks", action="overwrite")
        if parsed is None:
            return 1
        existing = parsed

    existing.setdefault("version", 1)
    existing["hooks"] = _merge_cursor_hooks(existing.get("hooks"), hooks)
    write_json_with_backup(hooks_path, existing, "hooks")
    print_binary_install_summary(f"Installed vibeforcer hooks into {hooks_path}", binary)
    return 0


def _uninstall_cursor(dry_run: bool = False) -> int:
    return uninstall_hooks_file(
        _cursor_hooks_path(),
        label="Cursor",
        remove_owned=_remove_cursor_hooks,
        dry_run=dry_run,
    )
