"""OpenCode installer support."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from functools import cache
from pathlib import Path

import slopgate.installer._shared
from slopgate import __version__
from slopgate._types import ObjectDict, ObjectMapping, object_dict
from slopgate.constants import REPLACE, UNKNOWN_VALUE
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
_PLUGIN_IDENTITY_PLACEHOLDER_LITERAL = (
    '{"placeholder":"__SLOPGATE_OPENCODE_IDENTITY__"}'
)
PLUGIN_OWNERSHIP_MARKERS = (
    "OpenCode Slopgate Plugin",
    "const SLOPGATE_BIN",
    "const SLOPGATE_ARGV",
)


class OpenCodeTemplateError(RuntimeError):
    """Raised when the bundled OpenCode plugin template cannot be rendered."""


def _opencode_config_dir() -> Path:
    """Resolve OpenCode's user config directory across native platforms."""
    return user_config_dir("opencode")


def opencode_user_plugin_path() -> Path:
    return _opencode_config_dir() / "plugins" / _PLUGIN_NAME


def _opencode_project_plugin_path(project_root: Path) -> Path:
    return project_root / ".opencode" / "plugins" / _PLUGIN_NAME


_render_opencode_invocation = InvocationTemplateRenderer(
    _PLUGIN_ARGV_PLACEHOLDER_LITERAL,
    "OpenCode plugin template is missing the slopgate binary placeholder",
)


def _json_file(path: Path) -> ObjectDict:
    try:
        return object_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return {}


def _dependency_version(payload: ObjectMapping) -> str:
    dependencies = object_dict(payload.get("dependencies"))
    value = dependencies.get("@opencode-ai/plugin")
    return value if isinstance(value, str) else ""


@cache
def _opencode_runtime_version() -> str:
    executable = shutil.which("opencode")
    if executable is None:
        return ""
    try:
        result = subprocess.run(
            [executable, "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def collect_opencode_install_identity(
    binary: str,
    *,
    config_dir: Path | None = None,
    probe_runtime: bool = True,
) -> ObjectDict:
    root = config_dir or _opencode_config_dir()
    declared = _dependency_version(_json_file(root / "package.json"))
    try:
        lock_content = (root / "bun.lock").read_text(encoding="utf-8")
    except OSError:
        lock_content = ""
    lock_match = re.search(
        r'"@opencode-ai/plugin"\s*:\s*("(?:\\.|[^"\\])*")', lock_content
    )
    lock_literal = lock_match.group(1) if lock_match else '""'
    try:
        lock_value = json.loads(lock_literal)
    except json.JSONDecodeError:
        lock_value = ""
    lock = lock_value if isinstance(lock_value, str) else ""
    installed_payload = _json_file(
        root / "node_modules" / "@opencode-ai" / "plugin" / "package.json"
    )
    installed_value = installed_payload.get("version")
    installed = installed_value if isinstance(installed_value, str) else ""
    runtime = _opencode_runtime_version() if probe_runtime else ""
    observed = [value for value in (runtime, declared, lock, installed) if value]
    status = "compatible" if observed and len(set(observed)) == 1 else "stale"
    remediation = (
        "none"
        if status == "compatible"
        else "Reinstall OpenCode plugin dependencies, then restart OpenCode."
    )
    return {
        "status": status,
        "opencode_version": runtime,
        "opencode_version_source": "opencode --version",
        "plugin_declared_version": declared,
        "plugin_declared_source": str(root / "package.json"),
        "plugin_lock_version": lock,
        "plugin_lock_source": str(root / "bun.lock"),
        "plugin_installed_version": installed,
        "plugin_installed_source": str(root / "node_modules" / "@opencode-ai" / "plugin" / "package.json"),
        "slopgate_version": __version__,
        "slopgate_binary": str(Path(binary).expanduser().resolve()),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "provenance": "install",
        "remediation": remediation,
    }


def render_opencode_plugin(
    template: str,
    binary: str,
    identity: ObjectMapping | None = None,
) -> str:
    rendered = _render_opencode_invocation(template, binary)
    snapshot = identity or collect_opencode_install_identity(binary)
    identity_json = json.dumps(dict(snapshot), separators=(",", ":"), sort_keys=True)
    if _PLUGIN_IDENTITY_PLACEHOLDER_LITERAL not in rendered:
        raise OpenCodeTemplateError(
            "OpenCode plugin template is missing the install identity placeholder"
        )
    return rendered.replace(_PLUGIN_IDENTITY_PLACEHOLDER_LITERAL, identity_json)


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
    backup_existing_file_and_report(target, "file")
    _ = target.write_text(content, encoding="utf-8")
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
    identity = collect_opencode_install_identity(binary, probe_runtime=not dry_run)
    if identity["status"] == "stale":
        print(
            "OpenCode identity is stale: "
            f"runtime={identity['opencode_version'] or UNKNOWN_VALUE}, "
            f"declared={identity['plugin_declared_version'] or UNKNOWN_VALUE}, "
            f"lock={identity['plugin_lock_version'] or UNKNOWN_VALUE}, "
            f"installed={identity['plugin_installed_version'] or UNKNOWN_VALUE}. "
            f"{identity['remediation']}"
        )
    paths = resolve_scoped_install_paths(
        scope,
        project_root,
        user_path=opencode_user_plugin_path(),
        project_path_for_root=_opencode_project_plugin_path,
    )
    content = template.read_text(encoding="utf-8")
    try:
        content = render_opencode_plugin(content, binary, identity)
    except OpenCodeTemplateError as exc:
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
