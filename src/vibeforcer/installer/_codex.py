"""Codex CLI installer support."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import cast

from vibeforcer.constants import METADATA_COMMAND, POST_TOOL_USE, PRE_TOOL_USE
from vibeforcer.installer._shared import (
    HOOK_TYPE_COMMAND,
    backup_existing_file_and_report,
    find_binary,
    hook_command,
    merge_owned_hooks_into,
    print_binary_install_summary,
    remove_owned_hooks,
    require_json_object,
    remove_file_with_backup,
    write_json_with_backup,
)

_CodeHookMeta = dict[str, str | int]
_CodeHookCommand = dict[str, str | int]
_CodeHookEntry = dict[str, str | list[_CodeHookCommand]]
_CodeHooks = dict[str, list[_CodeHookEntry]]

_CODEX_EVENTS: dict[str, _CodeHookMeta] = {
    "SessionStart": {
        "matcher": "startup|resume|clear",
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
    command = hook_command(binary, "handle", "--platform", "codex")
    for event, meta in _CODEX_EVENTS.items():
        command_entry: _CodeHookCommand = {
            "type": HOOK_TYPE_COMMAND,
            METADATA_COMMAND: command,
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
_HOOKS_RE = re.compile(r"^(\s*hooks\s*=\s*)[^#\n]*(\s*(?:#.*)?)$")
_CODEX_HOOKS_RE = re.compile(r"^(\s*)codex_hooks(\s*=\s*)[^#\n]*(\s*(?:#.*)?)$")


def _feature_section_bounds(lines: list[str]) -> tuple[int | None, int]:
    features_index = next(
        (index for index, line in enumerate(lines) if line.strip() == "[features]"),
        None,
    )
    if features_index is None:
        return None, len(lines)
    next_section_index = next(
        (
            index
            for index in range(features_index + 1, len(lines))
            if _SECTION_RE.match(lines[index])
        ),
        len(lines),
    )
    return features_index, next_section_index


def _find_codex_feature_flags(
    lines: list[str], start_index: int, end_index: int
) -> tuple[int | None, list[int]]:
    hooks_index: int | None = None
    codex_hooks_indexes: list[int] = []
    for index in range(start_index, end_index):
        if _HOOKS_RE.match(lines[index]):
            hooks_index = index
        elif _CODEX_HOOKS_RE.match(lines[index]):
            codex_hooks_indexes.append(index)
    return hooks_index, codex_hooks_indexes


def _write_codex_toml_lines(config_path: Path, lines: list[str]) -> None:
    config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _existing_codex_toml_is_valid(config_path: Path) -> bool:
    if not config_path.exists():
        return True
    try:
        tomllib.loads(config_path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        print(f"Invalid Codex config TOML; refusing to modify: {config_path}: {exc}")
        return False
    return True


def _drop_lines(lines: list[str], indexes: list[int]) -> None:
    for index in reversed(indexes):
        del lines[index]


def _set_existing_hooks_flag(
    config_path: Path, lines: list[str], hooks_index: int, codex_hooks_indexes: list[int]
) -> None:
    match = _HOOKS_RE.match(lines[hooks_index])
    if match:
        lines[hooks_index] = f"{match.group(1)}true{match.group(2)}"
    _drop_lines(lines, codex_hooks_indexes)
    _write_codex_toml_lines(config_path, lines)


def _replace_legacy_codex_hooks_flag(
    config_path: Path, lines: list[str], codex_hooks_indexes: list[int]
) -> None:
    first_index = codex_hooks_indexes[0]
    match = _CODEX_HOOKS_RE.match(lines[first_index])
    if match:
        lines[first_index] = f"{match.group(1)}hooks{match.group(2)}true{match.group(3)}"
    _drop_lines(lines, codex_hooks_indexes[1:])
    _write_codex_toml_lines(config_path, lines)


def _enable_codex_hooks_toml(config_path: Path) -> None:
    """Enable the current Codex hooks feature flag without rewriting config.toml."""
    text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    lines = text.splitlines()
    features_index, next_section_index = _feature_section_bounds(lines)
    if features_index is None:
        suffix = "" if not lines else "\n\n"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            text.rstrip("\n") + suffix + "[features]\nhooks = true\n",
            encoding="utf-8",
        )
        return

    hooks_index, codex_hooks_indexes = _find_codex_feature_flags(
        lines, features_index + 1, next_section_index
    )
    if hooks_index is not None:
        _set_existing_hooks_flag(config_path, lines, hooks_index, codex_hooks_indexes)
        return
    if codex_hooks_indexes:
        _replace_legacy_codex_hooks_flag(config_path, lines, codex_hooks_indexes)
        return
    lines.insert(features_index + 1, "hooks = true")
    _write_codex_toml_lines(config_path, lines)


def _install_codex(dry_run: bool = False) -> int:
    binary = find_binary()
    hooks_path = Path.home() / ".codex" / "hooks.json"
    hooks = _codex_hooks_block(binary)

    if dry_run:
        print(f"Would write: {hooks_path}")
        print(json.dumps({"hooks": hooks}, indent=2))
        return 0

    hooks_path.parent.mkdir(parents=True, exist_ok=True)
    if not hooks_path.exists():
        existing = {}
    elif (existing := require_json_object(hooks_path, "Codex hooks", action="overwrite")) is None:
        return 1

    config_path = Path.home() / ".codex" / "config.toml"
    if not _existing_codex_toml_is_valid(config_path):
        return 1

    merge_owned_hooks_into(existing, cast(dict[str, list[dict[str, object]]], hooks))
    write_json_with_backup(hooks_path, existing, "hooks")

    backup_existing_file_and_report(config_path, "config")
    _enable_codex_hooks_toml(config_path)
    print_binary_install_summary(
        f"Installed vibeforcer hooks into {hooks_path}\n"
        f"Enabled hooks feature flag in {config_path}",
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

    existing = require_json_object(hooks_path, "Codex hooks", action="modify")
    if existing is None:
        return 1

    remaining_hooks = remove_owned_hooks(existing.get("hooks"))
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
