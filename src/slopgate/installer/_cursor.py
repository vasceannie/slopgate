"""Cursor native hooks installer support."""

from __future__ import annotations
import json
from pathlib import Path
from typing import cast
from slopgate.installer._install_scope import (
    INSTALL_SCOPES,
    json_has_owned_slopgate_hooks,
    normalize_install_scope,
    resolve_project_root,
    scope_paths,
    ResidualInstallScopeWarning,
    warn_residual_install_scope,
)
import slopgate.installer._shared
from slopgate.installer._shared import (
    HOOK_TIMEOUT_LONG,
    HOOK_TIMEOUT_SHORT,
    HOOK_TIMEOUT_STANDARD,
    HooksUninstall,
    InstallAt,
    UnsafeInstallPathError,
    command_is_slopgate_hook,
    contained_scope_root,
    hook_command,
    print_binary_install_summary,
    report_contained_install_path,
    require_json_object,
    uninstall_hooks_file,
    write_contained_json,
)

_CursorHookEntry = dict[str, object]
_CursorHooks = dict[str, list[_CursorHookEntry]]
CURSOR_INSTALL_SCOPES = INSTALL_SCOPES
__all__ = ["install_cursor", "uninstall_cursor", "CURSOR_INSTALL_SCOPES"]
CURSOR_EVENTS: dict[str, dict[str, object]] = {
    "preToolUse": {"timeout": HOOK_TIMEOUT_STANDARD, "failClosed": True},
    "postToolUse": {"timeout": HOOK_TIMEOUT_STANDARD, "failClosed": False},
    "postToolUseFailure": {"timeout": HOOK_TIMEOUT_SHORT, "failClosed": False},
    "beforeShellExecution": {"timeout": HOOK_TIMEOUT_STANDARD, "failClosed": True},
    "afterShellExecution": {"timeout": HOOK_TIMEOUT_STANDARD, "failClosed": False},
    "beforeMCPExecution": {"timeout": HOOK_TIMEOUT_STANDARD, "failClosed": True},
    "afterMCPExecution": {"timeout": HOOK_TIMEOUT_STANDARD, "failClosed": False},
    "beforeReadFile": {"timeout": HOOK_TIMEOUT_SHORT, "failClosed": False},
    "beforeTabFileRead": {"timeout": HOOK_TIMEOUT_SHORT, "failClosed": False},
    "afterFileEdit": {"timeout": HOOK_TIMEOUT_LONG, "failClosed": False},
    "afterTabFileEdit": {"timeout": HOOK_TIMEOUT_LONG, "failClosed": False},
    "beforeSubmitPrompt": {"timeout": HOOK_TIMEOUT_SHORT, "failClosed": False},
    "sessionStart": {"timeout": HOOK_TIMEOUT_SHORT, "failClosed": False},
    "stop": {"timeout": HOOK_TIMEOUT_LONG, "failClosed": False},
    "subagentStart": {"timeout": HOOK_TIMEOUT_SHORT, "failClosed": False},
    "subagentStop": {"timeout": HOOK_TIMEOUT_STANDARD, "failClosed": False},
    "preCompact": {"timeout": HOOK_TIMEOUT_SHORT, "failClosed": False},
}


def cursor_user_hooks_path() -> Path:
    return Path.home() / ".cursor" / "hooks.json"


def cursor_project_hooks_path(project_root: Path) -> Path:
    return project_root.resolve() / ".cursor" / "hooks.json"


def _cursor_user_root() -> Path:
    return Path.home() / ".cursor"


def _cursor_contained_root(target: Path, project_root: Path) -> Path:
    return contained_scope_root(
        target, project_root=project_root, user_root=_cursor_user_root()
    )


def cursor_hooks_block(binary: str) -> _CursorHooks:
    command = hook_command(binary, "handle", "--platform", "cursor")
    hooks: _CursorHooks = {}
    for event, meta in CURSOR_EVENTS.items():
        entry: _CursorHookEntry = {"command": command}
        entry.update(meta)
        hooks[event] = [entry]
    return hooks


def _cursor_entry_is_owned(entry: object) -> bool:
    if not isinstance(entry, dict):
        return False
    command = cast(dict[object, object], entry).get("command")
    return command_is_slopgate_hook(command)


def _coerce_cursor_entries(value: object) -> list[_CursorHookEntry]:
    if not isinstance(value, list):
        return []
    entries: list[_CursorHookEntry] = []
    for item in cast("list[object]", value):
        if isinstance(item, dict):
            item_untyped = cast(dict[object, object], item)
            all_str = True
            for key in item_untyped:
                if not isinstance(key, str):
                    all_str = False
                    break
            if all_str:
                entries.append(cast(_CursorHookEntry, item))
    return entries


def _merge_cursor_hooks(
    existing_hooks: object, managed_hooks: _CursorHooks
) -> _CursorHooks:
    merged: _CursorHooks = {}
    if isinstance(existing_hooks, dict):
        for event, entries in cast(dict[object, object], existing_hooks).items():
            if isinstance(event, str):
                merged[event] = _coerce_cursor_entries(entries)
    for event, entries in managed_hooks.items():
        preserved = [
            entry
            for entry in merged.get(event, [])
            if not _cursor_entry_is_owned(entry)
        ]
        merged[event] = [*preserved, *entries]
    return merged


def _remove_cursor_hooks(existing_hooks: object) -> _CursorHooks:
    remaining: _CursorHooks = {}
    if not isinstance(existing_hooks, dict):
        return remaining
    for event, entries in cast(dict[object, object], existing_hooks).items():
        if not isinstance(event, str):
            continue
        kept = [
            entry
            for entry in _coerce_cursor_entries(entries)
            if not _cursor_entry_is_owned(entry)
        ]
        if kept:
            remaining[event] = kept
    return remaining


def _install_cursor_at(
    hooks_path: Path,
    binary: str,
    hooks: _CursorHooks,
    site: InstallAt,
) -> int:
    if report_contained_install_path(hooks_path, site.root) is None:
        return 1
    if site.dry_run:
        print(f"Would write: {hooks_path}")
        print(f"Binary: {binary}")
        print(json.dumps({"version": 1, "hooks": hooks}, indent=2))
        return 0
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
    try:
        write_contained_json(hooks_path, existing, root=site.root, label="hooks")
    except UnsafeInstallPathError as exc:
        print(str(exc))
        return 1
    print_binary_install_summary(f"Installed slopgate hooks into {hooks_path}", binary)
    return 0


def install_cursor(
    dry_run: bool = False, *, scope: str = "user", project_root: Path | None = None
) -> int:
    install_scope = normalize_install_scope(scope)
    binary = slopgate.installer._shared.find_binary()
    hooks = cursor_hooks_block(binary)
    root = resolve_project_root(project_root)
    paths = scope_paths(
        install_scope,
        user_path=cursor_user_hooks_path(),
        project_path=cursor_project_hooks_path(root),
    )
    completed: list[Path] = []
    last_status = 0
    for hooks_path in paths:
        contained_root = _cursor_contained_root(hooks_path, root)
        status = _install_cursor_at(
            hooks_path, binary, hooks, InstallAt(root=contained_root, dry_run=dry_run)
        )
        if status != 0:
            if not dry_run:
                for rollback_path in completed:
                    _ = uninstall_hooks_file(
                        rollback_path,
                        HooksUninstall(
                            label="Cursor",
                            remove_owned=_remove_cursor_hooks,
                            dry_run=False,
                            root=_cursor_contained_root(rollback_path, root),
                        ),
                    )
            return status
        completed.append(hooks_path)
        last_status = status
    return last_status


def uninstall_cursor(
    dry_run: bool = False, *, scope: str = "user", project_root: Path | None = None
) -> int:
    install_scope = normalize_install_scope(scope)
    root = resolve_project_root(project_root)
    last_status = 0
    paths = scope_paths(
        install_scope,
        user_path=cursor_user_hooks_path(),
        project_path=cursor_project_hooks_path(root),
    )
    for hooks_path in paths:
        status = uninstall_hooks_file(
            hooks_path,
            HooksUninstall(
                label="Cursor",
                remove_owned=_remove_cursor_hooks,
                dry_run=dry_run,
                root=_cursor_contained_root(hooks_path, root),
            ),
        )
        if status != 0:
            return status
        last_status = status
    if not dry_run:
        warn_residual_install_scope(
            ResidualInstallScopeWarning(
                platform_label="Cursor",
                scope=scope,
                user_path=cursor_user_hooks_path(),
                project_path=cursor_project_hooks_path(root),
                project_root=project_root,
                has_owned=json_has_owned_slopgate_hooks,
            )
        )
    return last_status
