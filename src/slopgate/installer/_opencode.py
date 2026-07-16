"""OpenCode installer support."""

from __future__ import annotations

from pathlib import Path

import slopgate.installer._shared
from slopgate.constants import REPLACE
from slopgate.installer._install_scope import (
    ResidualInstallScopeWarning,
    normalize_install_scope,
    opencode_plugin_has_owned_slopgate,
    resolve_project_root,
    resolve_scoped_install_paths,
    scope_paths,
    warn_residual_install_scope,
)
from slopgate.installer.install_flow import rollback_completed_installs
from slopgate.installer._shared import (
    backup_existing_file_and_report,
    print_binary_install_summary,
    remove_file_with_backup,
)
from slopgate.installer.template_rendering import InvocationTemplateRenderer
from slopgate.util.platform import user_config_dir

__all__ = ["install_opencode", "uninstall_opencode"]
_PLUGIN_NAME = "slopgate-plugin.ts"
_PLUGIN_ARGV_PLACEHOLDER_LITERAL = '["__SLOPGATE_BIN__"]'
PLUGIN_OWNERSHIP_MARKERS = (
    "OpenCode Slopgate Plugin",
    "Slopgate plugin loaded",
    "const SLOPGATE_BIN",
    "const SESSION_ID",
)


def _opencode_config_dir() -> Path:
    """Resolve OpenCode's user config directory across native platforms."""
    return user_config_dir("opencode")


def opencode_user_plugin_path() -> Path:
    return _opencode_config_dir() / "plugins" / _PLUGIN_NAME


def opencode_project_plugin_path(project_root: Path) -> Path:
    return project_root / ".opencode" / "plugins" / _PLUGIN_NAME


render_opencode_plugin = InvocationTemplateRenderer(
    _PLUGIN_ARGV_PLACEHOLDER_LITERAL,
    "OpenCode plugin template is missing the slopgate binary placeholder",
)


def _is_owned_opencode_plugin(content: str) -> bool:
    return all((marker in content for marker in PLUGIN_OWNERSHIP_MARKERS))


def _backup_and_report(path: Path) -> None:
    backup_existing_file_and_report(path, "file")


def _install_opencode_at(
    target: Path, content: str, binary: str, *, dry_run: bool
) -> int:
    target_dir = target.parent
    if dry_run:
        print(f"Would write: {target}")
        print(f"Binary: {binary}")
        if target.exists():
            print(f"Would back up existing file before writing: {target}")
        print(content[:500] + "...")
        return 0
    target_dir.mkdir(parents=True, exist_ok=True)
    _backup_and_report(target)
    slopgate.installer._shared.safe_write_text(target, content)
    print_binary_install_summary(f"Installed slopgate plugin to {target}", binary)
    return 0


def install_opencode(
    dry_run: bool = False, *, scope: str = "user", project_root: Path | None = None
) -> int:
    from slopgate.resources import resource_path

    template = resource_path("opencode_plugin.ts")
    if not template.exists():
        print(f"OpenCode plugin template not found at {template}")
        return 1
    binary = slopgate.installer._shared.find_binary()
    paths = resolve_scoped_install_paths(
        scope,
        project_root,
        user_path=opencode_user_plugin_path(),
        project_path_for_root=opencode_project_plugin_path,
    )
    content = template.read_text(encoding="utf-8")
    try:
        content = render_opencode_plugin(content, binary)
    except ValueError as exc:
        print(str(exc))
        return 1
    completed: list[Path] = []
    last_status = 0
    for target in paths:
        status = _install_opencode_at(target, content, binary, dry_run=dry_run)
        if status != 0:
            if not dry_run:
                rollback_completed_installs(
                    completed,
                    lambda rollback_path: _uninstall_opencode_at(
                        rollback_path, dry_run=False
                    ),
                )
            return status
        completed.append(target)
        last_status = status
    return last_status


def _uninstall_opencode_at(target: Path, *, dry_run: bool) -> int:
    if not target.exists():
        return 0
    content = target.read_text(encoding="utf-8", errors=REPLACE)
    if not _is_owned_opencode_plugin(content):
        print(f"Refusing to remove unrecognized OpenCode plugin: {target}")
        return 1
    if dry_run:
        print(f"Would back up and delete: {target}")
        return 0
    remove_file_with_backup(target, "file")
    print(f"Removed slopgate plugin from {target}")
    return 0


def uninstall_opencode(
    dry_run: bool = False, *, scope: str = "user", project_root: Path | None = None
) -> int:
    install_scope = normalize_install_scope(scope)
    root = resolve_project_root(project_root)
    paths = scope_paths(
        install_scope,
        user_path=opencode_user_plugin_path(),
        project_path=opencode_project_plugin_path(root),
    )
    any_found = False
    last_status = 0
    for target in paths:
        if target.exists():
            any_found = True
        status = _uninstall_opencode_at(target, dry_run=dry_run)
        if status != 0:
            return status
        last_status = status
    if not any_found and install_scope == "user":
        print("No OpenCode slopgate plugin found.")
    if not dry_run:
        warn_residual_install_scope(
            ResidualInstallScopeWarning(
                platform_label="OpenCode",
                scope=scope,
                user_path=opencode_user_plugin_path(),
                project_path=opencode_project_plugin_path(root),
                project_root=project_root,
                has_owned=opencode_plugin_has_owned_slopgate,
            )
        )
    return last_status
