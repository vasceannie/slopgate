"""Shared installer helpers."""

from __future__ import annotations

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from vibeforcer._types import object_dict, object_list
from vibeforcer.constants import METADATA_COMMAND

HOOK_TYPE_COMMAND = METADATA_COMMAND


def find_binary() -> str:
    """Find the vibeforcer binary on PATH."""
    binary = shutil.which("vibeforcer")
    if binary:
        return binary
    return "vibeforcer"


def entry_has_vibeforcer_command(entry: object) -> bool:
    entry_dict = object_dict(entry)
    if not entry_dict:
        return False
    hooks = entry_dict.get("hooks")
    hook_entries = object_list(hooks)
    if not hook_entries:
        return False
    for hook in hook_entries:
        hook_dict = object_dict(hook)
        if not hook_dict:
            continue
        command = hook_dict.get(METADATA_COMMAND)
        if isinstance(command, str) and "vibeforcer" in command and " handle" in command:
            return True
    return False


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
        preserved = [
            entry
            for entry in merged.get(event, [])
            if not entry_has_vibeforcer_command(entry)
        ]
        merged[event] = [*preserved, *entries]
    return merged


def remove_owned_hooks(existing_hooks: object) -> dict[str, list[dict[str, object]]]:
    remaining: dict[str, list[dict[str, object]]] = {}
    hooks_dict = object_dict(existing_hooks)
    if not hooks_dict:
        return remaining
    for event, entries in hooks_dict.items():
        kept = [
            entry
            for entry in coerce_hook_entries(entries)
            if not entry_has_vibeforcer_command(entry)
        ]
        if kept:
            remaining[event] = kept
    return remaining


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


def print_binary_install_summary(message: str, binary: str) -> None:
    print(message)
    print(f"Binary: {binary}")
