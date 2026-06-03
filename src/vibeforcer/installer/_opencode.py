"""OpenCode installer support."""

from __future__ import annotations

import json
from pathlib import Path

from vibeforcer.installer._shared import (
    backup_existing_file_and_report,
    find_binary,
    print_binary_install_summary,
    remove_file_with_backup,
)
from vibeforcer.util.platform import user_config_dir

_PLUGIN_NAME = "vibeforcer-plugin.ts"
_PLUGIN_PLACEHOLDER_LITERAL = '"__VIBEFORCER_BIN__"'
_PLUGIN_OWNERSHIP_MARKERS = (
    "OpenCode Vibeforcer Plugin",
    "Vibeforcer plugin loaded",
    "const VIBEFORCER_BIN",
    "const SESSION_ID",
)


def _opencode_config_dir() -> Path:
    """Resolve OpenCode's user config directory across native platforms."""
    return user_config_dir("opencode")


def _opencode_plugin_path() -> Path:
    return _opencode_config_dir() / "plugins" / _PLUGIN_NAME


def _render_opencode_plugin(template_text: str, binary: str) -> str:
    """Render the OpenCode plugin with a safely quoted binary fallback."""
    if _PLUGIN_PLACEHOLDER_LITERAL not in template_text:
        raise ValueError(
            "OpenCode plugin template is missing the vibeforcer binary placeholder"
        )
    return template_text.replace(_PLUGIN_PLACEHOLDER_LITERAL, json.dumps(binary))


def _is_owned_opencode_plugin(content: str) -> bool:
    return all(marker in content for marker in _PLUGIN_OWNERSHIP_MARKERS)


def _backup_and_report(path: Path) -> None:
    backup_existing_file_and_report(path, "file")


def _install_opencode(dry_run: bool = False) -> int:
    from vibeforcer.resources import resource_path

    template = resource_path("opencode_plugin.ts")
    if not template.exists():
        print(f"OpenCode plugin template not found at {template}")
        return 1

    binary = find_binary()
    target = _opencode_plugin_path()
    target_dir = target.parent

    content = template.read_text(encoding="utf-8")
    try:
        content = _render_opencode_plugin(content, binary)
    except ValueError as exc:
        print(str(exc))
        return 1

    if dry_run:
        print(f"Would write: {target}")
        print(f"Binary: {binary}")
        if target.exists():
            print(f"Would back up existing file before writing: {target}")
        print(content[:500] + "...")
        return 0

    target_dir.mkdir(parents=True, exist_ok=True)
    _backup_and_report(target)
    _ = target.write_text(content, encoding="utf-8")
    print_binary_install_summary(f"Installed vibeforcer plugin to {target}", binary)
    return 0


def _uninstall_opencode(dry_run: bool = False) -> int:
    target = _opencode_plugin_path()
    if not target.exists():
        print("No OpenCode vibeforcer plugin found.")
        return 0

    content = target.read_text(encoding="utf-8", errors="replace")
    if not _is_owned_opencode_plugin(content):
        print(f"Refusing to remove unrecognized OpenCode plugin: {target}")
        return 1

    if dry_run:
        print(f"Would back up and delete: {target}")
        return 0

    remove_file_with_backup(target, "file")
    return 0
