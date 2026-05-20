"""OpenCode installer support."""

from __future__ import annotations

from pathlib import Path

from vibeforcer.installer._shared import find_binary, print_binary_install_summary


def _install_opencode(dry_run: bool = False) -> int:
    from vibeforcer.resources import resource_path

    template = resource_path("opencode_plugin.ts")
    if not template.exists():
        print(f"OpenCode plugin template not found at {template}")
        return 1

    binary = find_binary()
    target_dir = Path.home() / ".config" / "opencode" / "plugins"
    target = target_dir / "vibeforcer-plugin.ts"

    content = template.read_text(encoding="utf-8")
    content = content.replace("__VIBEFORCER_BIN__", binary)

    if dry_run:
        print(f"Would write: {target}")
        print(f"Binary: {binary}")
        print(content[:500] + "...")
        return 0

    target_dir.mkdir(parents=True, exist_ok=True)
    _ = target.write_text(content, encoding="utf-8")
    print_binary_install_summary(f"Installed vibeforcer plugin to {target}", binary)
    return 0


def _uninstall_opencode(dry_run: bool = False) -> int:
    target = Path.home() / ".config" / "opencode" / "plugins" / "vibeforcer-plugin.ts"
    if not target.exists():
        print("No OpenCode vibeforcer plugin found.")
        return 0

    if dry_run:
        print(f"Would delete: {target}")
        return 0

    target.unlink()
    print(f"Removed: {target}")
    return 0
