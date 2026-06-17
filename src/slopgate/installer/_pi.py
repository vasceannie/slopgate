"""Pi extension installer support."""

from __future__ import annotations

import json
from pathlib import Path

import slopgate.installer._shared
from slopgate.installer._install_scope import (
    ResidualInstallScopeWarning,
    normalize_install_scope,
    resolve_project_root,
    scope_paths,
    warn_residual_install_scope,
)
from slopgate.installer._shared import (
    backup_existing_file_and_report,
    base_invocation,
    print_binary_install_summary,
    remove_file_with_backup,
)

__all__ = ["PI_OWNERSHIP_MARKERS", "install_pi", "pi_project_extension_path", "uninstall_pi"]

_EXTENSION_NAME = "slopgate.ts"
_PI_ARGV_PLACEHOLDER_LITERAL = '["__SLOPGATE_BIN__"]'
PI_OWNERSHIP_MARKERS = (
    "Pi Slopgate Extension",
    "const SLOPGATE_ARGV",
    "slopgate handle --platform pi",
)


def pi_user_extension_path() -> Path:
    return Path.home() / ".pi" / "agent" / "extensions" / _EXTENSION_NAME


def pi_project_extension_path(project_root: Path) -> Path:
    return project_root / ".pi" / "extensions" / _EXTENSION_NAME


def render_pi_extension(template_text: str, binary: str) -> str:
    if _PI_ARGV_PLACEHOLDER_LITERAL not in template_text:
        raise ValueError("Pi extension template is missing the slopgate binary placeholder")
    return template_text.replace(
        _PI_ARGV_PLACEHOLDER_LITERAL, json.dumps(base_invocation(binary))
    )


def _is_owned_pi_extension(content: str) -> bool:
    return all(marker in content for marker in PI_OWNERSHIP_MARKERS)


def pi_extension_has_owned_slopgate(path: Path) -> bool:
    if not path.exists():
        return False
    return _is_owned_pi_extension(path.read_text(encoding="utf-8", errors="replace"))


def _install_pi_at(target: Path, content: str, binary: str, *, dry_run: bool) -> int:
    if dry_run:
        print(f"Would write: {target}")
        print(f"Binary: {binary}")
        if target.exists():
            print(f"Would back up existing file before writing: {target}")
        print(content[:500] + "...")
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    backup_existing_file_and_report(target, "file")
    target.write_text(content, encoding="utf-8")
    print_binary_install_summary(f"Installed slopgate Pi extension to {target}", binary)
    return 0


def install_pi(
    dry_run: bool = False, *, scope: str = "user", project_root: Path | None = None
) -> int:
    from slopgate.resources import resource_path

    template = resource_path("pi_extension.ts")
    if not template.exists():
        print(f"Pi extension template not found at {template}")
        return 1
    install_scope = normalize_install_scope(scope)
    binary = slopgate.installer._shared.find_binary()
    root = resolve_project_root(project_root)
    paths = scope_paths(
        install_scope,
        user_path=pi_user_extension_path(),
        project_path=pi_project_extension_path(root),
    )
    try:
        content = render_pi_extension(template.read_text(encoding="utf-8"), binary)
    except ValueError as exc:
        print(str(exc))
        return 1
    completed: list[Path] = []
    for target in paths:
        status = _install_pi_at(target, content, binary, dry_run=dry_run)
        if status != 0:
            for rollback_path in completed:
                _uninstall_pi_at(rollback_path, dry_run=False)
            return status
        completed.append(target)
    return 0


def _uninstall_pi_at(target: Path, *, dry_run: bool) -> int:
    if not target.exists():
        return 0
    content = target.read_text(encoding="utf-8", errors="replace")
    if not _is_owned_pi_extension(content):
        print(f"Refusing to remove unrecognized Pi extension: {target}")
        return 1
    if dry_run:
        print(f"Would back up and delete: {target}")
        return 0
    remove_file_with_backup(target, "file")
    print(f"Removed slopgate Pi extension from {target}")
    return 0


def uninstall_pi(
    dry_run: bool = False, *, scope: str = "user", project_root: Path | None = None
) -> int:
    install_scope = normalize_install_scope(scope)
    root = resolve_project_root(project_root)
    paths = scope_paths(
        install_scope,
        user_path=pi_user_extension_path(),
        project_path=pi_project_extension_path(root),
    )
    for target in paths:
        status = _uninstall_pi_at(target, dry_run=dry_run)
        if status != 0:
            return status
    if not dry_run:
        warn_residual_install_scope(
            ResidualInstallScopeWarning(
                platform_label="Pi",
                scope=scope,
                user_path=pi_user_extension_path(),
                project_path=pi_project_extension_path(root),
                project_root=project_root,
                has_owned=pi_extension_has_owned_slopgate,
            )
        )
    return 0
