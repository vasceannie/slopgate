"""Codex CLI installer support."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import cast

from vibeforcer._types import object_dict
from vibeforcer.constants import METADATA_COMMAND, POST_TOOL_USE, PRE_TOOL_USE
from vibeforcer.installer._shared import (
    HOOK_TYPE_COMMAND,
    find_binary,
    merge_owned_hooks,
    print_binary_install_summary,
    remove_owned_hooks,
)

_CodeHookMeta = dict[str, str | int]
_CodeHookCommand = dict[str, str | int]
_CodeHookEntry = dict[str, str | list[_CodeHookCommand]]
_CodeHooks = dict[str, list[_CodeHookEntry]]

_CODEX_EVENTS: dict[str, _CodeHookMeta] = {
    "SessionStart": {
        "matcher": "startup|resume",
        "timeout": 10,
        "statusMessage": "Loading vibeforcer context",
    },
    PRE_TOOL_USE: {
        "matcher": "Bash|apply_patch|Edit|Write",
        "timeout": 10,
        "statusMessage": "vibeforcer: checking tool use",
    },
    "PermissionRequest": {
        "matcher": "Bash|apply_patch|Edit|Write",
        "timeout": 10,
        "statusMessage": "vibeforcer: checking approval request",
    },
    POST_TOOL_USE: {
        "matcher": "Bash|apply_patch|Edit|Write",
        "timeout": 10,
        "statusMessage": "vibeforcer: reviewing tool output",
    },
    "UserPromptSubmit": {"timeout": 10},
    "Stop": {"timeout": 30},
}


def _codex_hooks_block(binary: str) -> _CodeHooks:
    hooks: _CodeHooks = {}
    for event, meta in _CODEX_EVENTS.items():
        command_entry: _CodeHookCommand = {
            "type": HOOK_TYPE_COMMAND,
            METADATA_COMMAND: f"{binary} handle --platform codex",
        }
        entry: _CodeHookEntry = {"hooks": [command_entry]}
        matcher = meta.get("matcher")
        if isinstance(matcher, str):
            entry["matcher"] = matcher
        status_message = meta.get("statusMessage")
        if isinstance(status_message, str):
            command_entry["statusMessage"] = status_message
        timeout = meta.get("timeout")
        if isinstance(timeout, int):
            command_entry["timeout"] = timeout
        hooks[event] = [entry]
    return hooks


_SECTION_RE = re.compile(r"^\s*\[[^\]]+\]")
_CODEX_HOOKS_RE = re.compile(r"^(\s*codex_hooks\s*=\s*)[^#\n]*(\s*(?:#.*)?)$")


def _enable_codex_hooks_toml(config_path: Path) -> None:
    """Enable the current Codex hooks feature flag without rewriting config.toml."""
    text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    lines = text.splitlines()
    features_index: int | None = None
    next_section_index = len(lines)
    for index, line in enumerate(lines):
        if line.strip() == "[features]":
            features_index = index
            break
    if features_index is not None:
        for index in range(features_index + 1, len(lines)):
            if _SECTION_RE.match(lines[index]):
                next_section_index = index
                break
        for index in range(features_index + 1, next_section_index):
            match = _CODEX_HOOKS_RE.match(lines[index])
            if match:
                lines[index] = f"{match.group(1)}true{match.group(2)}"
                config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                return
        lines.insert(features_index + 1, "codex_hooks = true")
        config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return

    suffix = "" if not lines else "\n\n"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        text.rstrip("\n") + suffix + "[features]\ncodex_hooks = true\n",
        encoding="utf-8",
    )


def _install_codex(dry_run: bool = False) -> int:
    binary = find_binary()
    hooks_path = Path.home() / ".codex" / "hooks.json"
    hooks = _codex_hooks_block(binary)

    if dry_run:
        print(f"Would write: {hooks_path}")
        print(json.dumps({"hooks": hooks}, indent=2))
        return 0

    hooks_path.parent.mkdir(parents=True, exist_ok=True)
    if hooks_path.exists():
        try:
            parsed = cast(object, json.loads(hooks_path.read_text(encoding="utf-8")))
            existing = object_dict(parsed)
        except json.JSONDecodeError:
            existing = {}
    else:
        existing = {}

    existing["hooks"] = merge_owned_hooks(
        existing.get("hooks"), cast(dict[str, list[dict[str, object]]], hooks)
    )
    _ = hooks_path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")

    config_path = Path.home() / ".codex" / "config.toml"
    _enable_codex_hooks_toml(config_path)
    print_binary_install_summary(
        f"Installed vibeforcer hooks into {hooks_path}\n"
        f"Enabled codex_hooks feature flag in {config_path}",
        binary,
    )
    return 0


def _uninstall_codex(dry_run: bool = False) -> int:
    hooks_path = Path.home() / ".codex" / "hooks.json"
    if not hooks_path.exists():
        print("No Codex hooks found.")
        return 0

    if dry_run:
        print(f"Would remove vibeforcer hook entries from {hooks_path}")
        return 0

    try:
        parsed = cast(object, json.loads(hooks_path.read_text(encoding="utf-8")))
        existing = object_dict(parsed)
    except json.JSONDecodeError:
        hooks_path.unlink()
        print(f"Removed invalid hooks file: {hooks_path}")
        return 0

    remaining_hooks = remove_owned_hooks(existing.get("hooks"))
    if remaining_hooks:
        existing["hooks"] = remaining_hooks
        _ = hooks_path.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")
        print(f"Removed vibeforcer hooks from {hooks_path}")
    else:
        hooks_path.unlink()
        print(f"Removed: {hooks_path}")
    return 0
