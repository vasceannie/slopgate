"""OpenCode runtime and plugin dependency identity collection."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Callable
from datetime import datetime, timezone
from functools import cache
from pathlib import Path

from slopgate import __version__
from slopgate._types import ObjectDict, ObjectMapping, object_dict
from slopgate.constants import PLATFORM_OPENCODE, UNKNOWN_VALUE
from slopgate.util.platform import child_creation_flags, user_config_dir

_VERSION_TOKEN = re.compile(r"v?(\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)")
_OPENCODE_API_TARGET = "2.2.5"
_PLUGIN_PACKAGE = "@opencode/plugin"
_DEPENDENCY_RESOLUTION = "opencode-host"


def _json_file(path: Path) -> ObjectDict:
    try:
        return object_dict(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return {}


def _dependency_version(payload: ObjectMapping) -> str:
    dependencies = object_dict(payload.get("dependencies"))
    value = dependencies.get(_PLUGIN_PACKAGE)
    return value if isinstance(value, str) else ""


@cache
def opencode_runtime_version() -> str:
    executable = shutil.which(PLATFORM_OPENCODE)
    if executable is None:
        return ""
    try:
        result = subprocess.run(
            [executable, "--version"],
            check=False,
            creationflags=child_creation_flags(),
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _canonical_version(value: str) -> str:
    match = _VERSION_TOKEN.search(value.strip())
    return match.group(1) if match else value.strip()


def _opencode_lock_version(lock_content: str) -> str:
    lock_match = re.search(
        rf'"{re.escape(_PLUGIN_PACKAGE)}"\s*:\s*("(?:\\.|[^"\\])*")', lock_content
    )
    lock_literal = lock_match.group(1) if lock_match else '""'
    try:
        lock_value = json.loads(lock_literal)
    except json.JSONDecodeError:
        lock_value = ""
    return lock_value if isinstance(lock_value, str) else ""


def _opencode_identity_status(runtime: str) -> tuple[str, str]:
    if not runtime:
        return UNKNOWN_VALUE, "OpenCode identity could not be observed."
    canonical_runtime = _canonical_version(runtime)
    if canonical_runtime == _OPENCODE_API_TARGET:
        return "compatible", "none"
    major_token = canonical_runtime.partition(".")[0]
    if major_token.isdigit() and int(major_token) < 2:
        return (
            "stale",
            "OpenCode 2.2.5 is required for the v2 plugin; upgrade OpenCode, then restart OpenCode.",
        )
    return (
        UNKNOWN_VALUE,
        "OpenCode runtime is not verified against the supported v2 plugin API target.",
    )


def collect_opencode_install_identity(
    binary: str,
    *,
    config_dir: Path | None = None,
    probe_runtime: bool = True,
    runtime_version: Callable[[], str] | None = None,
) -> ObjectDict:
    root = config_dir or user_config_dir(PLATFORM_OPENCODE)
    declared = _dependency_version(_json_file(root / "package.json"))
    try:
        lock_content = (root / "bun.lock").read_text(encoding="utf-8")
    except OSError:
        lock_content = ""
    lock = _opencode_lock_version(lock_content)
    installed_payload = _json_file(
        root / "node_modules" / "@opencode" / "plugin" / "package.json"
    )
    installed_value = installed_payload.get("version")
    installed = installed_value if isinstance(installed_value, str) else ""
    runtime_probe = runtime_version or opencode_runtime_version
    runtime = runtime_probe() if probe_runtime else ""
    status, remediation = _opencode_identity_status(runtime)
    return {
        "plugin_package": _PLUGIN_PACKAGE,
        "plugin_api_target": _OPENCODE_API_TARGET,
        "dependency_resolution": _DEPENDENCY_RESOLUTION,
        "status": status,
        "opencode_version": runtime,
        "opencode_version_source": "opencode --version",
        "plugin_declared_version": declared,
        "plugin_declared_source": str(root / "package.json"),
        "plugin_lock_version": lock,
        "plugin_lock_source": str(root / "bun.lock"),
        "plugin_installed_version": installed,
        "plugin_installed_source": str(
            root / "node_modules" / "@opencode" / "plugin" / "package.json"
        ),
        "slopgate_version": __version__,
        "slopgate_binary": str(Path(binary).expanduser().resolve()),
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "provenance": "install",
        "remediation": remediation,
    }


__all__ = ["collect_opencode_install_identity", "opencode_runtime_version"]
