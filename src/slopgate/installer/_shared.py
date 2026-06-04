"""Shared installer helpers."""

from __future__ import annotations

import json
import shutil
import shlex
import subprocess
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath
from typing import cast

from vibeforcer._types import object_dict, object_list
from vibeforcer.constants import METADATA_COMMAND
from vibeforcer.util.platform import is_windows

HOOK_TYPE_COMMAND = METADATA_COMMAND

HOOK_TIMEOUT_SHORT = 10
HOOK_TIMEOUT_STANDARD = HOOK_TIMEOUT_SHORT + HOOK_TIMEOUT_SHORT
HOOK_TIMEOUT_LONG = HOOK_TIMEOUT_STANDARD + HOOK_TIMEOUT_SHORT


def find_binary() -> str:
    """Find the vibeforcer binary on PATH."""
    binary = shutil.which("vibeforcer")
    if binary:
        return binary
    return sys.executable


def base_invocation(binary: str) -> list[str]:
    if Path(binary).resolve() == Path(sys.executable).resolve():
        return [binary, "-m", "vibeforcer"]
    return [binary]


def shell_command(argv: list[str], *, windows: bool | None = None) -> str:
    use_windows = is_windows() if windows is None else windows
    if not use_windows:
        return shlex.join(argv)
    ps_args = ["'" + arg.replace("'", "''") + "'" for arg in argv]
    ps_script = "& " + " ".join(ps_args)
    return subprocess.list2cmdline(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            ps_script,
        ]
    )


def hook_command(binary: str, *args: str, windows: bool | None = None) -> str:
    return shell_command([*base_invocation(binary), *args], windows=windows)


def _command_basename(token: str) -> str:
    posix_name = Path(token).name
    windows_name = PureWindowsPath(token).name
    return (windows_name if len(windows_name) < len(posix_name) else posix_name).lower()


def _executable_is_vibeforcer(token: str) -> bool:
    return _command_basename(token) in {"vibeforcer", "vibeforcer.exe"}


def _executable_is_python(token: str) -> bool:
    basename = _command_basename(token)
    return basename == "python" or basename == "python.exe" or basename.startswith("python3")


def _argv_invokes_vibeforcer_handle(argv: list[str]) -> bool:
    if len(argv) >= 2 and _executable_is_vibeforcer(argv[0]):
        return argv[1] == "handle"
    if len(argv) >= 4 and _executable_is_python(argv[0]):
        return argv[1:4] == ["-m", "vibeforcer", "handle"]
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


def command_is_vibeforcer_hook(command: object) -> bool:
    """Return true only for hook commands installed by Vibeforcer."""

    if not isinstance(command, str):
        return False
    try:
        argv = shlex.split(command)
    except ValueError:
        return False
    if _argv_invokes_vibeforcer_handle(argv):
        return True
    if not argv or _command_basename(argv[0]) not in {"powershell.exe", "powershell"}:
        return False
    return _argv_invokes_vibeforcer_handle(_powershell_command_argv(argv))


def filter_owned_hook_commands(entry: object) -> dict[str, object] | None:
    entry_dict = object_dict(entry)
    if not entry_dict:
        return None
    hook_entries = object_list(entry_dict.get("hooks"))
    if not hook_entries:
        return dict(entry_dict)
    kept_hooks = []
    for hook in hook_entries:
        hook_dict = object_dict(hook)
        if not hook_dict:
            continue
        if not command_is_vibeforcer_hook(hook_dict.get(METADATA_COMMAND)):
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
        preserved = []
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
        kept = []
        for entry in coerce_hook_entries(entries):
            filtered_entry = filter_owned_hook_commands(entry)
            if filtered_entry is not None:
                kept.append(filtered_entry)
        if kept:
            remaining[event] = kept
    return remaining


def require_json_object(path: Path, label: str, *, action: str) -> dict[str, object] | None:
    try:
        parsed = cast(object, json.loads(path.read_text(encoding="utf-8")))
    except json.JSONDecodeError:
        print(f"Invalid {label} JSON; refusing to {action}: {path}")
        return None
    if not isinstance(parsed, dict):
        print(f"Invalid {label} JSON object; refusing to {action}: {path}")
        return None
    return cast(dict[str, object], parsed)


def merge_owned_hooks_into(
    config: dict[str, object], managed_hooks: dict[str, list[dict[str, object]]]
) -> None:
    """Replace only vibeforcer-owned hook entries in a config document."""
    config["hooks"] = merge_owned_hooks(config.get("hooks"), managed_hooks)


def backup_existing_file(path: Path) -> Path | None:
    """Create a timestamped sibling backup for an existing config/plugin file."""
    if not path.exists():
        return None
    timestamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
    backup_path = path.with_name(f"{path.name}.vibeforcer-bak-{timestamp}")
    _ = shutil.copy2(path, backup_path)
    return backup_path


def backup_existing_file_and_report(path: Path, label: str) -> None:
    """Back up an existing file and print a concise installer status line."""
    backup_path = backup_existing_file(path)
    if backup_path is not None:
        print(f"Backed up existing {label} to {backup_path}")


def write_json_with_backup(path: Path, payload: object, label: str) -> None:
    """Back up an existing file, then write formatted JSON."""
    backup_existing_file_and_report(path, label)
    _ = path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def remove_file_with_backup(path: Path, label: str) -> None:
    backup_existing_file_and_report(path, label)
    path.unlink()
    print(f"Removed: {path}")


def uninstall_hooks_file(
    hooks_path: Path,
    *,
    label: str,
    remove_owned: Callable[[object], dict[str, list[dict[str, object]]]],
    dry_run: bool = False,
) -> int:
    """Remove vibeforcer-owned hook entries from a platform hooks.json file."""
    if not hooks_path.exists():
        print(f"No {label} hooks found.")
        return 0
    if dry_run:
        print(f"Would remove vibeforcer hook entries from {hooks_path}")
        return 0

    existing = require_json_object(hooks_path, f"{label} hooks", action="modify")
    if existing is None:
        return 1

    remaining_hooks = remove_owned(existing.get("hooks"))
    if remaining_hooks:
        existing["hooks"] = remaining_hooks
        write_json_with_backup(hooks_path, existing, "hooks")
        print(f"Removed vibeforcer hooks from {hooks_path}")
        return 0

    existing.pop("hooks", None)
    if existing:
        write_json_with_backup(hooks_path, existing, "hooks")
        print(f"Removed vibeforcer hooks from {hooks_path}")
        return 0

    remove_file_with_backup(hooks_path, "hooks")
    return 0


def print_binary_install_summary(message: str, binary: str) -> None:
    print(message)
    print(f"Binary: {binary}")
