"""Pi extension installer support."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

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

__all__ = [
    "PI_OWNERSHIP_MARKERS",
    "install_pi",
    "pi_project_extension_path",
    "uninstall_pi",
]

_EXTENSION_DIR_NAME = "pi-slopgate"
_EXTENSION_ENTRY_NAME = "index.ts"
_LEGACY_EXTENSION_NAME = "slopgate.ts"
_LEGACY_PACKAGE_ENTRY_NAME = "index.js"
_CONFIG_NAME = "config.json"
_PACKAGE_NAME = "package.json"
_PI_ARGV_PLACEHOLDER_LITERAL = '["__SLOPGATE_BIN__"]'
PI_OWNERSHIP_MARKERS = (
    "Pi Slopgate Extension",
    "const SLOPGATE_ARGV",
    "slopgate handle --platform pi",
)
_LEGACY_PACKAGE_OWNERSHIP_MARKERS = (
    "pi-slopgate",
    "slopgate handle --platform pi",
)
_CONFIG_PAYLOAD = {
    "name": "pi-slopgate",
    "description": "Pi Agent extension for slopgate code hygiene enforcement.",
    "version": "1.0.0",
    "enabled": True,
}
_PACKAGE_PAYLOAD = {
    "private": True,
    "type": "module",
    "dependencies": {
        "@earendil-works/pi-tui": "^0.79.6",
    },
}


def pi_user_extension_path() -> Path:
    return (
        Path.home()
        / ".pi"
        / "agent"
        / "extensions"
        / _EXTENSION_DIR_NAME
        / _EXTENSION_ENTRY_NAME
    )


def pi_project_extension_path(project_root: Path) -> Path:
    return (
        project_root
        / ".pi"
        / "extensions"
        / _EXTENSION_DIR_NAME
        / _EXTENSION_ENTRY_NAME
    )


def _legacy_extension_path_for(target: Path) -> Path:
    return target.parent.parent / _LEGACY_EXTENSION_NAME


def _legacy_package_entry_path_for(target: Path) -> Path:
    return target.parent / _LEGACY_PACKAGE_ENTRY_NAME


def _config_path_for(target: Path) -> Path:
    return target.parent / _CONFIG_NAME


def _package_path_for(target: Path) -> Path:
    return target.parent / _PACKAGE_NAME


def render_pi_extension(template_text: str, binary: str) -> str:
    if _PI_ARGV_PLACEHOLDER_LITERAL not in template_text:
        raise ValueError(
            "Pi extension template is missing the slopgate binary placeholder"
        )
    return template_text.replace(
        _PI_ARGV_PLACEHOLDER_LITERAL, json.dumps(base_invocation(binary))
    )


def _is_owned_pi_extension(content: str) -> bool:
    return all(marker in content for marker in PI_OWNERSHIP_MARKERS)


def _is_owned_legacy_package_extension(content: str) -> bool:
    return all(marker in content for marker in _LEGACY_PACKAGE_OWNERSHIP_MARKERS)


def _is_owned_pi_config(content: str) -> bool:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return False
    if not isinstance(parsed, dict):
        return False
    parsed_config = cast("dict[str, object]", parsed)
    name = parsed_config.get("name")
    return isinstance(name, str) and name == _CONFIG_PAYLOAD["name"]


def _is_owned_pi_package(content: str) -> bool:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return False
    if not isinstance(parsed, dict):
        return False
    parsed_package = cast("dict[str, object]", parsed)
    dependencies = parsed_package.get("dependencies")
    if not isinstance(dependencies, dict):
        return False
    package_deps = cast("dict[object, object]", dependencies)
    return "@earendil-works/pi-tui" in package_deps


def pi_extension_has_owned_slopgate(path: Path) -> bool:
    if not path.exists():
        return False
    content = path.read_text(encoding="utf-8", errors="replace")
    if path.name == _LEGACY_PACKAGE_ENTRY_NAME:
        return _is_owned_legacy_package_extension(content)
    if path.name == _CONFIG_NAME:
        return _is_owned_pi_config(content)
    if path.name == _PACKAGE_NAME:
        return _is_owned_pi_package(content)
    return _is_owned_pi_extension(content)


def _remove_owned_file(path: Path, label: str, *, dry_run: bool) -> int:
    if not path.exists():
        return 0
    if not pi_extension_has_owned_slopgate(path):
        print(f"Refusing to remove unrecognized {label}: {path}")
        return 1
    if dry_run:
        print(f"Would back up and delete {label}: {path}")
        return 0
    remove_file_with_backup(path, label)
    return 0


def _remove_empty_parent(path: Path, *, dry_run: bool) -> None:
    parent = path.parent
    if dry_run or not parent.exists():
        return
    try:
        parent.rmdir()
    except OSError:
        return


def _write_config(config_path: Path, *, dry_run: bool) -> None:
    if dry_run:
        print(f"Would write: {config_path}")
        return
    backup_existing_file_and_report(config_path, "file")
    config_path.write_text(
        json.dumps(_CONFIG_PAYLOAD, indent=2) + "\n", encoding="utf-8"
    )


def _write_package(package_path: Path, *, dry_run: bool) -> None:
    if dry_run:
        print(f"Would write: {package_path}")
        return
    backup_existing_file_and_report(package_path, "file")
    package_path.write_text(
        json.dumps(_PACKAGE_PAYLOAD, indent=2) + "\n", encoding="utf-8"
    )


def _cleanup_migrated_pi_extensions(target: Path, *, dry_run: bool) -> int:
    status = 0
    for stale_path, label in (
        (_legacy_extension_path_for(target), "legacy Pi extension"),
        (
            _legacy_package_entry_path_for(target),
            "legacy pi-slopgate JavaScript extension",
        ),
    ):
        if stale_path == target:
            continue
        if stale_path.exists() and not pi_extension_has_owned_slopgate(stale_path):
            print(f"Warning: unrecognized {label} remains active: {stale_path}")
            status = 1
            continue
        status = _remove_owned_file(stale_path, label, dry_run=dry_run) or status
    return status


def _install_pi_at(target: Path, content: str, binary: str, *, dry_run: bool) -> int:
    config_path = _config_path_for(target)
    package_path = _package_path_for(target)
    if dry_run:
        print(f"Would write: {target}")
        print(f"Would write: {config_path}")
        print(f"Would write: {package_path}")
        print(f"Binary: {binary}")
        if target.exists():
            print(f"Would back up existing file before writing: {target}")
        if config_path.exists():
            print(f"Would back up existing file before writing: {config_path}")
        if package_path.exists():
            print(f"Would back up existing file before writing: {package_path}")
        _cleanup_migrated_pi_extensions(target, dry_run=True)
        print(content[:500] + "...")
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    backup_existing_file_and_report(target, "file")
    target.write_text(content, encoding="utf-8")
    _write_config(config_path, dry_run=False)
    _write_package(package_path, dry_run=False)
    status = _cleanup_migrated_pi_extensions(target, dry_run=False)
    print_binary_install_summary(f"Installed slopgate Pi extension to {target}", binary)
    return status


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
    status = 0
    for path, label in (
        (target, "Pi extension"),
        (_config_path_for(target), "Pi extension config"),
        (_package_path_for(target), "Pi extension package manifest"),
        (_legacy_extension_path_for(target), "legacy Pi extension"),
        (
            _legacy_package_entry_path_for(target),
            "legacy pi-slopgate JavaScript extension",
        ),
    ):
        status = _remove_owned_file(path, label, dry_run=dry_run) or status
    if status == 0:
        _remove_empty_parent(target, dry_run=dry_run)
        if not dry_run:
            print(f"Removed slopgate Pi extension from {target}")
    return status


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
