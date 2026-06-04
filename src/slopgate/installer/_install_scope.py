"""Shared user/project install scope helpers for harness installers."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Literal, cast

from slopgate.installer._shared import command_is_slopgate_hook, remove_owned_hooks

InstallScope = Literal["user", "project", "both"]
INSTALL_SCOPES: frozenset[str] = frozenset({"user", "project", "both"})

# Backward-compatible alias used by early Cursor installer exports.
CURSOR_INSTALL_SCOPES = INSTALL_SCOPES


def normalize_install_scope(scope: str) -> InstallScope:
    normalized = scope.strip().lower()
    if normalized not in INSTALL_SCOPES:
        raise ValueError(
            f"install scope must be one of: {', '.join(sorted(INSTALL_SCOPES))}"
        )
    return cast(InstallScope, normalized)


def resolve_project_root(project_root: Path | None) -> Path:
    return (project_root or Path.cwd()).resolve()


def scope_paths(
    scope: InstallScope,
    *,
    user_path: Path,
    project_path: Path,
) -> list[Path]:
    paths: list[Path] = []
    if scope in {"user", "both"}:
        paths.append(user_path)
    if scope in {"project", "both"}:
        paths.append(project_path)
    return paths


def _hooks_dict_has_owned_slopgate(hooks: dict[object, object]) -> bool:
    remaining = remove_owned_hooks(hooks)
    if json.dumps(remaining, sort_keys=True) != json.dumps(hooks, sort_keys=True):
        return True
    for entries in hooks.values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict) and command_is_slopgate_hook(
                cast(dict[object, object], entry).get("command")
            ):
                return True
    return False


def _json_has_owned_slopgate_hooks(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    if not isinstance(parsed, dict):
        return False

    hooks = parsed.get("hooks")
    if isinstance(hooks, dict) and hooks:
        return _hooks_dict_has_owned_slopgate(cast(dict[object, object], hooks))
    return False


def _opencode_plugin_has_owned_slopgate(path: Path) -> bool:
    if not path.exists():
        return False
    content = path.read_text(encoding="utf-8", errors="replace")
    if "OpenCode Slopgate Plugin" in content and "const SLOPGATE_BIN" in content:
        return True
    return "OpenCode Slopgate Plugin" in content and "const SLOPGATE_BIN" in content


def warn_residual_install_scope(
    *,
    platform_label: str,
    scope: str,
    user_path: Path,
    project_path: Path,
    project_root: Path | None,
    has_owned: Callable[[Path], bool],
) -> None:
    """Warn when uninstall scope leaves slopgate hooks in the other location."""
    try:
        install_scope = normalize_install_scope(scope)
    except ValueError:
        return
    root = resolve_project_root(project_root)
    resolved_project = project_path if project_path.is_absolute() else root / project_path

    if install_scope == "both":
        return
    if install_scope == "project" and has_owned(user_path):
        print(
            f"Note: slopgate {platform_label} hooks remain at {user_path} "
            f"(re-run uninstall with --install-scope user or both)"
        )
    if install_scope == "user" and has_owned(resolved_project):
        print(
            f"Note: slopgate {platform_label} hooks remain at {resolved_project} "
            f"(re-run uninstall with --install-scope project or both)"
        )
