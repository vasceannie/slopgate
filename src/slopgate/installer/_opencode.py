"""OpenCode installer support."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import slopgate.installer._shared
from slopgate._types import ObjectDict, ObjectMapping
from slopgate.constants import PLATFORM_OPENCODE, REPLACE, UNKNOWN_VALUE
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
    ContainedWrite,
    InstallAt,
    UnsafeInstallPathError,
    contained_scope_root,
    print_binary_install_summary,
    remove_file_with_backup,
    report_contained_install_path,
    write_contained_text,
)
from slopgate.installer.template_rendering import InvocationTemplateRenderer
from slopgate.installer.opencode_identity import collect_opencode_install_identity
from slopgate.opencode_tool_capabilities import (
    EFFECTFUL_TOOL_IDS,
    READ_ONLY_TOOL_IDS,
)
from slopgate.util.platform import user_config_dir

__all__ = ["install_opencode", "uninstall_opencode"]
_PLUGIN_NAME = "slopgate-plugin.ts"
_PLUGIN_ARGV_PLACEHOLDER_LITERAL = '["__SLOPGATE_BIN__"]'
_PLUGIN_IDENTITY_PLACEHOLDER_LITERAL = (
    '{"placeholder":"__SLOPGATE_OPENCODE_IDENTITY__"}'
)
_READ_ONLY_TOOLS_PLACEHOLDER_LITERAL = '["__SLOPGATE_READ_ONLY_TOOL_IDS__"]'
_EFFECTFUL_TOOLS_PLACEHOLDER_LITERAL = '["__SLOPGATE_EFFECTFUL_TOOL_IDS__"]'
OPENCODE_TYPES_TARGET = "1.18.21"
PLUGIN_OWNERSHIP_MARKERS = (
    "OpenCode Slopgate Plugin",
    "const SLOPGATE_BIN",
)
class OpenCodeTemplateError(RuntimeError):
    """Raised when the bundled OpenCode plugin template cannot be rendered."""


@dataclass(frozen=True, slots=True)
class _OpenCodeInstallTarget:
    path: Path
    identity_root: Path
    scope: str
    dry_run: bool


def _opencode_config_dir() -> Path:
    """Resolve OpenCode's user config directory across native platforms."""
    return user_config_dir(PLATFORM_OPENCODE)


def opencode_user_plugin_path() -> Path:
    return _opencode_config_dir() / "plugins" / _PLUGIN_NAME


def _opencode_project_plugin_path(project_root: Path) -> Path:
    return project_root / ".opencode" / "plugins" / _PLUGIN_NAME


_render_opencode_invocation = InvocationTemplateRenderer(
    _PLUGIN_ARGV_PLACEHOLDER_LITERAL,
    "OpenCode plugin template is missing the slopgate binary placeholder",
)


def render_opencode_plugin(
    template: str,
    binary: str,
    identity: ObjectMapping | None = None,
) -> str:
    rendered = _render_opencode_invocation(template, binary)
    snapshot = identity or collect_opencode_install_identity(binary)
    identity_json = json.dumps(dict(snapshot), separators=(",", ":"), sort_keys=True)
    replacements = (
        (
            _PLUGIN_IDENTITY_PLACEHOLDER_LITERAL,
            identity_json,
            "install identity",
        ),
        (
            _READ_ONLY_TOOLS_PLACEHOLDER_LITERAL,
            json.dumps(sorted(READ_ONLY_TOOL_IDS), separators=(",", ":")),
            "read-only tool capabilities",
        ),
        (
            _EFFECTFUL_TOOLS_PLACEHOLDER_LITERAL,
            json.dumps(sorted(EFFECTFUL_TOOL_IDS), separators=(",", ":")),
            "effectful tool capabilities",
        ),
    )
    for placeholder, value, label in replacements:
        if placeholder not in rendered:
            raise OpenCodeTemplateError(
                f"OpenCode plugin template is missing the {label} placeholder"
            )
        rendered = rendered.replace(placeholder, value)
    return rendered


def _install_opencode_at(
    target: Path,
    content: str,
    binary: str,
    site: InstallAt,
) -> int:
    if report_contained_install_path(target, site.root) is None:
        return 1
    if site.dry_run:
        print(f"Would write: {target}")
        print(f"Binary: {binary}")
        if target.exists() and not target.is_symlink():
            print(f"Would back up existing file before writing: {target}")
        print(content[:500] + "...")
        return 0
    try:
        written = write_contained_text(
            target, content, ContainedWrite(root=site.root, label="file")
        )
    except UnsafeInstallPathError as exc:
        print(str(exc))
        return 1
    print_binary_install_summary(f"Installed slopgate plugin to {written}", binary)
    return 0


def _warn_stale_opencode_identity(identity: ObjectDict) -> None:
    if identity["status"] != "stale":
        return
    print(
        "OpenCode identity is stale: "
        f"runtime={identity['opencode_version'] or UNKNOWN_VALUE}, "
        f"declared={identity['plugin_declared_version'] or UNKNOWN_VALUE}, "
        f"lock={identity['plugin_lock_version'] or UNKNOWN_VALUE}, "
        f"installed={identity['plugin_installed_version'] or UNKNOWN_VALUE}. "
        f"{identity['remediation']}"
    )


def _opencode_install_content(
    template: str,
    binary: str,
    target: _OpenCodeInstallTarget,
) -> str | None:
    identity = collect_opencode_install_identity(
        binary,
        config_dir=target.identity_root,
        probe_runtime=not target.dry_run,
    )
    identity.update(
        {
            "install_scope": target.scope,
            "install_root": str(target.identity_root),
            "plugin_path": str(target.path),
        }
    )
    _warn_stale_opencode_identity(identity)
    try:
        return render_opencode_plugin(template, binary, identity)
    except OpenCodeTemplateError as exc:
        print(str(exc))
        return None


def _install_opencode_target(
    template: str,
    binary: str,
    target: _OpenCodeInstallTarget,
    project_root: Path,
) -> int:
    content = _opencode_install_content(template, binary, target)
    if content is None:
        return 1
    return _install_opencode_at(
        target.path,
        content,
        binary,
        InstallAt(
            root=contained_scope_root(
                target.path,
                project_root=project_root,
                user_root=_opencode_config_dir(),
            ),
            dry_run=target.dry_run,
        ),
    )


def install_opencode(
    dry_run: bool = False, *, scope: str = "user", project_root: Path | None = None
) -> int:
    from slopgate.resources import resource_path

    template = resource_path("opencode_plugin.ts")
    if not template.exists():
        print(f"OpenCode plugin template not found at {template}")
        return 1
    binary = slopgate.installer._shared.find_binary()
    root = resolve_project_root(project_root)
    user_target = opencode_user_plugin_path()
    paths = resolve_scoped_install_paths(
        scope,
        root,
        user_path=user_target,
        project_path_for_root=_opencode_project_plugin_path,
    )
    template_content = template.read_text(encoding="utf-8")
    completed: list[Path] = []
    last_status = 0
    for target in paths:
        target_spec = _OpenCodeInstallTarget(
            path=target,
            identity_root=(
                _opencode_config_dir()
                if target == user_target
                else root / ".opencode"
            ),
            scope="user" if target == user_target else "project",
            dry_run=dry_run,
        )
        status = _install_opencode_target(
            template_content, binary, target_spec, root
        )
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
    if not all((marker in content for marker in PLUGIN_OWNERSHIP_MARKERS)):
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
        project_path=_opencode_project_plugin_path(root),
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
                project_path=_opencode_project_plugin_path(root),
                project_root=project_root,
                has_owned=opencode_plugin_has_owned_slopgate,
            )
        )
    return last_status
