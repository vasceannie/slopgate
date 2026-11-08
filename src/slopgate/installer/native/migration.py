"""Legacy owned-hook extraction for native cutover rollback."""

from __future__ import annotations

from slopgate._types import object_dict, object_list
from slopgate.constants import METADATA_COMMAND
from slopgate.installer._shared import coerce_hook_entries, command_is_slopgate_hook

__all__ = ["extract_owned_hooks"]


def _owned_commands(entry: dict[str, object]) -> list[dict[str, object]] | None:
    owned: list[dict[str, object]] = []
    for hook in object_list(entry.get("hooks")):
        hook_dict = object_dict(hook)
        if not hook_dict:
            continue
        if command_is_slopgate_hook(hook_dict.get(METADATA_COMMAND)):
            owned.append(hook_dict)
    return owned or None


def extract_owned_hooks(hooks: object) -> dict[str, list[dict[str, object]]]:
    """Return only Slopgate-owned hook groups, keeping their original metadata."""
    owned: dict[str, list[dict[str, object]]] = {}
    for event, entries in object_dict(hooks).items():
        groups: list[dict[str, object]] = []
        for entry in coerce_hook_entries(entries):
            commands = _owned_commands(entry)
            if commands is None:
                continue
            group = dict(entry)
            group["hooks"] = commands
            groups.append(group)
        if groups:
            owned[event] = groups
    return owned
