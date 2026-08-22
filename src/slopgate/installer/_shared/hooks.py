"""Owned-hook command detection and JSON hook-document merges."""

from __future__ import annotations

import json
import shlex
from pathlib import Path, PureWindowsPath
from typing import cast

from slopgate._types import object_dict, object_list
from slopgate.constants import METADATA_COMMAND
from slopgate.installer._shared.models import OwnedHooksWrite
from slopgate.installer.hook_proxy import HOOK_PROXY_MARKER
from slopgate.util import logger

_LEGACY_HOOK_EXECUTABLES = frozenset(
    {
        "slopgate",
        "slopgate.exe",
        "vfc",
        "vfc.exe",
        "isx",
        "isx.exe",
    }
)


def _command_basename(token: str) -> str:
    posix_name = Path(token).name
    windows_name = PureWindowsPath(token).name
    return (windows_name if len(windows_name) < len(posix_name) else posix_name).lower()


def _executable_is_slopgate(token: str) -> bool:
    return _command_basename(token) in {"slopgate", "slopgate.exe", "sgt", "sgt.exe"}


def _executable_is_legacy_slopgate(token: str) -> bool:
    return _command_basename(token) in _LEGACY_HOOK_EXECUTABLES


def _executable_is_python(token: str) -> bool:
    basename = _command_basename(token)
    return (
        basename == "python"
        or basename == "python.exe"
        or basename.startswith("python3")
    )


def _argv_invokes_slopgate_handle(argv: list[str]) -> bool:
    logger.info(
        "installer hook argv inspect",
        argc=len(argv),
        command=_command_basename(argv[0]) if argv else "",
    )
    if len(argv) >= 2 and _executable_is_slopgate(argv[0]):
        return argv[1] == "handle"
    if len(argv) >= 2 and _executable_is_legacy_slopgate(argv[0]):
        return argv[1] == "handle"
    if len(argv) >= 4 and _executable_is_python(argv[0]):
        return argv[1:4] == ["-m", "slopgate", "handle"]
    return False


def _powershell_command_argv(argv: list[str]) -> list[str]:
    for index, token in enumerate(argv):
        if token.lower() in {"-command", "-c"} and index + 1 < len(argv):
            try:
                script_argv = shlex.split(argv[index + 1])
            except ValueError:
                return []
            if script_argv[:1] == ["&"]:
                return script_argv[1:]
            return script_argv
    return []


def command_is_slopgate_hook(command: object) -> bool:
    """Return true only for hook commands installed by Slopgate."""

    if not isinstance(command, str):
        return False
    try:
        argv = shlex.split(command)
    except ValueError:
        return False
    if _argv_invokes_slopgate_handle(argv) or _argv_invokes_daemon_proxy(argv):
        return True
    if not argv or _command_basename(argv[0]) not in {"powershell.exe", "powershell"}:
        return False
    return _argv_invokes_slopgate_handle(_powershell_command_argv(argv))


def _argv_invokes_daemon_proxy(argv: list[str]) -> bool:
    if len(argv) < 3:
        return False
    if _command_basename(argv[0]) not in {"sh", "bash"}:
        return False
    return argv[1] == "-c" and HOOK_PROXY_MARKER in argv[2]


def filter_owned_hook_commands(entry: object) -> dict[str, object] | None:
    entry_dict = object_dict(entry)
    if not entry_dict:
        return None
    hook_entries = object_list(entry_dict.get("hooks"))
    if not hook_entries:
        return dict(entry_dict)
    kept_hooks: list[dict[str, object]] = []
    for hook in hook_entries:
        hook_dict = object_dict(hook)
        if not hook_dict:
            continue
        if not command_is_slopgate_hook(hook_dict.get(METADATA_COMMAND)):
            kept_hooks.append(hook_dict)
    if not kept_hooks:
        return None
    filtered = dict(entry_dict)
    filtered["hooks"] = kept_hooks
    return filtered


def coerce_hook_entries(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        return []
    entries: list[dict[str, object]] = []
    for entry in cast(list[object], value):
        entry_dict = object_dict(entry)
        if entry_dict:
            entries.append(entry_dict)
    return entries


def merge_owned_hooks(
    existing_hooks: object, managed_hooks: dict[str, list[dict[str, object]]]
) -> dict[str, list[dict[str, object]]]:
    merged: dict[str, list[dict[str, object]]] = {}
    for event, entries in object_dict(existing_hooks).items():
        merged[event] = coerce_hook_entries(entries)
    for event, entries in managed_hooks.items():
        preserved: list[dict[str, object]] = []
        for entry in merged.get(event, []):
            filtered_entry = filter_owned_hook_commands(entry)
            if filtered_entry is not None:
                preserved.append(filtered_entry)
        merged[event] = [*preserved, *entries]
    return merged


def remove_owned_hooks(existing_hooks: object) -> dict[str, list[dict[str, object]]]:
    remaining: dict[str, list[dict[str, object]]] = {}
    hooks_dict = object_dict(existing_hooks)
    if not hooks_dict:
        return remaining
    for event, entries in hooks_dict.items():
        kept: list[dict[str, object]] = []
        for entry in coerce_hook_entries(entries):
            filtered_entry = filter_owned_hook_commands(entry)
            if filtered_entry is not None:
                kept.append(filtered_entry)
        if kept:
            remaining[event] = kept
    return remaining


def require_json_object(
    path: Path, label: str, *, action: str
) -> dict[str, object] | None:
    try:
        parsed = cast(object, json.loads(path.read_text(encoding="utf-8")))
    except json.JSONDecodeError:
        print(f"Invalid {label} JSON; refusing to {action}: {path}")
        return None
    if not isinstance(parsed, dict):
        print(f"Invalid {label} JSON object; refusing to {action}: {path}")
        return None
    return cast(dict[str, object], parsed)


def load_existing_json_object(
    path: Path, label: str, *, action: str
) -> dict[str, object] | None:
    """Return {} for a missing file, or the parsed object / None on invalid JSON."""
    if not path.exists():
        return {}
    return require_json_object(path, label, action=action)


def prepare_owned_hooks_document(
    path: Path, request: OwnedHooksWrite
) -> dict[str, object] | int:
    """Preview on dry-run, otherwise load and merge owned hook entries.

    Returns an ``int`` status when the caller should return immediately,
    or the merged document when the caller should write it.
    """
    if request.dry_run:
        print(f"Would {request.verb}: {path}")
        print(json.dumps({"hooks": request.hooks}, indent=2))
        return 0
    existing = load_existing_json_object(path, request.label, action="overwrite")
    if existing is None:
        return 1
    merge_owned_hooks_into(existing, request.hooks)
    return existing


def merge_owned_hooks_into(
    config: dict[str, object], managed_hooks: dict[str, list[dict[str, object]]]
) -> None:
    """Replace only slopgate-owned hook entries in a config document."""
    config["hooks"] = merge_owned_hooks(config.get("hooks"), managed_hooks)
