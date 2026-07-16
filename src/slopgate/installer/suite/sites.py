"""Suite-wide harness install site path specs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from slopgate.cli.platforms import VALID_PLATFORMS
from slopgate.installer._claude import (
    claude_project_settings_path,
    claude_user_settings_path,
)
from slopgate.installer._cursor import cursor_project_hooks_path, cursor_user_hooks_path
from slopgate.installer._opencode import (
    opencode_project_plugin_path,
    opencode_user_plugin_path,
)
from slopgate.installer._pi import pi_project_extension_path, pi_user_extension_path

(
    CLAUDE_PLATFORM,
    CODEX_PLATFORM,
    OPENCODE_PLATFORM,
    CURSOR_PLATFORM,
    PI_PLATFORM,
) = VALID_PLATFORMS


@dataclass(frozen=True)
class _InstallSiteSpec:
    """Platform path ownership for suite-wide discovery."""

    platform: str
    user_path: Callable[[], Path]
    project_path: Callable[[Path], Path]
    present_parent: int


INSTALL_SITE_SPECS = (
    _InstallSiteSpec(
        CLAUDE_PLATFORM, claude_user_settings_path, claude_project_settings_path, 0
    ),
    _InstallSiteSpec(
        CODEX_PLATFORM,
        lambda: Path.home() / ".codex" / "hooks.json",
        lambda root: root / ".codex" / "hooks.json",
        0,
    ),
    _InstallSiteSpec(
        OPENCODE_PLATFORM, opencode_user_plugin_path, opencode_project_plugin_path, 1
    ),
    _InstallSiteSpec(
        CURSOR_PLATFORM, cursor_user_hooks_path, cursor_project_hooks_path, 0
    ),
    _InstallSiteSpec(PI_PLATFORM, pi_user_extension_path, pi_project_extension_path, 2),
)
