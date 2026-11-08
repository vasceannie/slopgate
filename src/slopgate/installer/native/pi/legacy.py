"""Pi extension recognition and package rendering for earlier installs."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import cast

from slopgate.constants import REPLACE
from slopgate.installer.native.model import VERSION_KEY
from slopgate.installer.template_rendering import InvocationTemplateRenderer

__all__ = [
    "EXTENSION_DIR_NAME",
    "EXTENSION_ENTRY_NAME",
    "LEGACY_ENTRY_NAME",
    "LEGACY_PACKAGE_ENTRY_NAME",
    "LEGACY_PACKAGE_PAYLOAD",
    "PI_OWNERSHIP_MARKERS",
    "is_owned_pi_package",
    "pi_agent_dir",
    "pi_extension_has_owned_slopgate",
    "pi_has_owned_extension_entry",
    "pi_project_extension_path",
    "pi_template_path",
    "pi_user_extension_path",
    "render_pi_extension",
]

EXTENSION_DIR_NAME = "pi-slopgate"
EXTENSION_ENTRY_NAME = "index.ts"
LEGACY_ENTRY_NAME = "slopgate.ts"
LEGACY_PACKAGE_ENTRY_NAME = "index.js"
_CONFIG_NAME = "config.json"
_PACKAGE_NAME = "package.json"
_AGENT_DIR_ENV = "PI_CODING_AGENT_DIR"
_PI_ARGV_PLACEHOLDER_LITERAL = '["__SLOPGATE_BIN__"]'
_CONFIG_PAYLOAD = {
    "name": "pi-slopgate",
    "description": "Pi Agent extension for slopgate code hygiene enforcement.",
    VERSION_KEY: "1.0.0",
    "enabled": True,
}
# Historical loose-extension metadata; never written by the native installer.
LEGACY_PACKAGE_PAYLOAD = {
    "private": True,
    "type": "module",
    "dependencies": {"@types/node": "^22.16.5"},
    "peerDependencies": {"@earendil-works/pi-tui": "*"},
}
PI_OWNERSHIP_MARKERS = (
    "Pi Slopgate Extension",
    "const SLOPGATE_ARGV",
    "slopgate handle --platform pi",
)
_LEGACY_PACKAGE_OWNERSHIP_MARKERS = (
    "pi-slopgate",
    "slopgate handle --platform pi",
)
render_pi_extension = InvocationTemplateRenderer(
    _PI_ARGV_PLACEHOLDER_LITERAL,
    "Pi extension template is missing the slopgate binary placeholder",
)


def pi_agent_dir() -> Path:
    """Return Pi's active absolute agent directory."""
    configured = os.environ.get(_AGENT_DIR_ENV, "")
    candidate = Path(configured).expanduser() if configured else Path()
    if configured and candidate.is_absolute():
        return candidate.resolve()
    return (Path.home() / ".pi" / "agent").resolve()


def pi_user_extension_path() -> Path:
    """Return the former user-scoped loose-extension path."""
    return pi_agent_dir() / "extensions" / EXTENSION_DIR_NAME / EXTENSION_ENTRY_NAME


def pi_project_extension_path(project_root: Path) -> Path:
    """Return the former project-scoped loose-extension path."""
    return (
        project_root / ".pi" / "extensions" / EXTENSION_DIR_NAME / EXTENSION_ENTRY_NAME
    )


def pi_template_path() -> Path:
    """Locate the shared Pi extension template resource."""
    from slopgate.resources import resource_path

    return resource_path("pi_extension.ts")


def _json_object(content: str) -> dict[str, object] | None:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return cast("dict[str, object]", parsed)


def _is_owned_pi_config(content: str) -> bool:
    parsed = _json_object(content) or {}
    return parsed.get("name") == _CONFIG_PAYLOAD["name"]


def is_owned_pi_package(content: str) -> bool:
    parsed = _json_object(content) or {}
    legacy_peers = cast(dict[str, object], LEGACY_PACKAGE_PAYLOAD["peerDependencies"])
    for group_name in ("dependencies", "peerDependencies"):
        dependencies = parsed.get(group_name)
        if isinstance(dependencies, dict) and any(
            name in dependencies for name in legacy_peers
        ):
            return True
    return False


def pi_extension_has_owned_slopgate(path: Path) -> bool:
    """Recognize prior Pi extension files by their Slopgate markers."""
    if path.is_symlink() or not path.exists() or not path.is_file():
        return False
    content = path.read_text(encoding="utf-8", errors=REPLACE)
    if path.name == LEGACY_PACKAGE_ENTRY_NAME:
        return all(marker in content for marker in _LEGACY_PACKAGE_OWNERSHIP_MARKERS)
    if path.name == _CONFIG_NAME:
        return _is_owned_pi_config(content)
    if path.name == _PACKAGE_NAME:
        return is_owned_pi_package(content)
    return all(marker in content for marker in PI_OWNERSHIP_MARKERS)


def pi_has_owned_extension_entry(extension_dir: Path) -> bool:
    """Require a recognized executable entry before claiming its old package dir."""
    return any(
        pi_extension_has_owned_slopgate(extension_dir / name)
        for name in (EXTENSION_ENTRY_NAME, LEGACY_PACKAGE_ENTRY_NAME)
    )
