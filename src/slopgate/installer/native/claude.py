"""Claude Code local-marketplace adapter for native plugin registration."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import cast

from slopgate._types import object_dict
from slopgate.constants import (
    INSTALL_SCOPE_PROJECT,
    INSTALL_SCOPE_USER,
    METADATA_PATH,
    PLATFORM_CLAUDE,
)
from slopgate.installer._shared import shell_command
from slopgate.installer.native.commands import (
    LIST_SUBCOMMAND,
    REMOVE_SUBCOMMAND,
    NativeCommandError,
    run_native_command,
)
from slopgate.installer.native.marketplace.host import (
    MarketplaceCommands,
    MarketplaceHost,
)
from slopgate.installer.native.model import (
    LegacyCutover,
    NativeRequest,
    Registration,
    SOURCE_KEY,
    VERSION_KEY,
)
from slopgate.installer.native.packages import (
    MARKETPLACE_NAME,
    MarketplaceSpec,
    PackagePlan,
    marketplace_plan,
)
from slopgate.installer.native.settings_guard import NativeSettingsFile
from slopgate.installer.native.wsl import WslPaths

CLAUDE_PLUGIN_NAME = "slopgate-enforcement"
CLAUDE_PLUGIN_DESCRIPTION = "Slopgate code hygiene enforcement"
CLAUDE_CATALOG_DIR = ".claude-plugin"
CLAUDE_EXECUTABLE = "claude"
CLAUDE_LIST_COMMAND = "claude plugin list --json"
CLAUDE_ACTIVATION_NOTE = (
    "Start a new Claude Code session (or reload) before the registered plugin "
    "hooks are active."
)
_MARKETPLACE_LABEL = "Claude Code"
_PLUGIN_COMMAND = "plugin"
_SCOPE_FLAG = "--scope"
_ENABLED_PLUGINS_KEY = "enabledPlugins"
_KNOWN_MARKETPLACES_KEY = "extraKnownMarketplaces"
_INSTALL_ACTION = "install"
_UNINSTALL_ACTION = "uninstall"
_DISABLE_ACTION = "disable"
_MARKETPLACE_LIST = (
    CLAUDE_EXECUTABLE,
    _PLUGIN_COMMAND,
    "marketplace",
    LIST_SUBCOMMAND,
    "--json",
)
_PLUGIN_LIST = (CLAUDE_EXECUTABLE, _PLUGIN_COMMAND, LIST_SUBCOMMAND, "--json")

PayloadRenderer = Callable[[str, str], dict[str, str]]


@dataclass(frozen=True, slots=True)
class ClaudeLayout:
    """Installer-supplied settings locations and payload renderer."""

    user_settings: Callable[[], Path]
    project_settings: Callable[[Path], Path]
    user_root: Callable[[], Path]
    render_payload: PayloadRenderer


class ClaudeCommands(MarketplaceCommands):
    """Argument arrays for Claude's native local plugin manager."""

    def marketplace_add(self, entry_root: Path) -> list[str]:
        # Claude rejects absolute Windows paths ("C:\...") as an invalid
        # marketplace source; only owner/repo, URLs and ./relative are accepted.
        return [
            CLAUDE_EXECUTABLE,
            _PLUGIN_COMMAND,
            "marketplace",
            "add",
            f"./{entry_root.name}",
        ]

    def marketplace_add_cwd(self, entry_root: Path, root: Path) -> Path:
        _ = root
        return entry_root.parent

    def marketplace_update(self) -> list[str]:
        return _marketplace_action("update")

    def marketplace_remove(self) -> list[str]:
        return _marketplace_action(REMOVE_SUBCOMMAND)

    def install(self, scope: str, previous: Registration | None) -> list[list[str]]:
        commands = [_state_command(_INSTALL_ACTION, scope)]
        if previous is not None and previous.enabled is False:
            commands.append(_state_command(_DISABLE_ACTION, scope))
        return commands

    def replace(self, scope: str, previous: Registration) -> list[list[str]]:
        return [self.uninstall(scope), *self.install(scope, previous)]

    def uninstall(self, scope: str) -> list[str]:
        return [
            CLAUDE_EXECUTABLE,
            _PLUGIN_COMMAND,
            _UNINSTALL_ACTION,
            _plugin_id(),
            _SCOPE_FLAG,
            scope,
            "--keep-data",
        ]


class ClaudeHost(MarketplaceHost):
    """Claude plugin identity, staging and inventory operations."""

    platform = PLATFORM_CLAUDE
    label = _MARKETPLACE_LABEL
    executable = CLAUDE_EXECUTABLE
    plugin_name = CLAUDE_PLUGIN_NAME
    list_command = CLAUDE_LIST_COMMAND
    activation_note = CLAUDE_ACTIVATION_NOTE

    def __init__(self, layout: ClaudeLayout, wsl: WslPaths | None = None) -> None:
        self.layout = layout
        self.commands = ClaudeCommands()
        self._wsl = wsl

    def build_plan(self, binary: str) -> PackagePlan:
        renderer = partial(self.layout.render_payload, binary)
        spec = MarketplaceSpec(
            catalog_dir=CLAUDE_CATALOG_DIR,
            plugin_name=self.plugin_name,
            description=CLAUDE_PLUGIN_DESCRIPTION,
            render=renderer,
        )
        return marketplace_plan(self.platform, spec)

    def legacy_cutover(self, request: NativeRequest) -> LegacyCutover:
        from slopgate.installer.native.claude_legacy import ClaudeLegacyCutover

        return ClaudeLegacyCutover(request, self.layout)

    def marketplace_sources(self, cwd: Path) -> dict[str, str]:
        sources: dict[str, str] = {}
        for item in _json_array(list(_MARKETPLACE_LIST), cwd):
            marketplace = object_dict(item)
            name = marketplace.get("name")
            if isinstance(name, str):
                sources[name] = self._windows_path(_marketplace_path(marketplace))
        return sources

    def registrations(self, cwd: Path) -> list[Registration]:
        registrations: list[Registration] = []
        for item in _json_array(list(_PLUGIN_LIST), cwd):
            entry = object_dict(item)
            if entry.get("id") != _plugin_id():
                continue
            scope = entry.get("scope")
            if scope not in {INSTALL_SCOPE_USER, INSTALL_SCOPE_PROJECT}:
                continue
            project = entry.get("projectPath")
            if isinstance(project, str):
                entry = {**entry, "projectPath": self._windows_path(project)}
            registrations.append(
                _registration(entry, cast(str, scope), self.layout, cwd)
            )
        return registrations

    def _windows_path(self, reported: str) -> str:
        """A path as the host reported it, in the form this installer compares."""
        if self._wsl is None:
            return reported
        return str(self._wsl.to_windows(reported))

    def native_settings(self, scope: str, root: Path) -> tuple[NativeSettingsFile, ...]:
        path = (
            self.layout.project_settings(root)
            if scope == INSTALL_SCOPE_PROJECT
            else self.layout.user_settings()
        )
        return (
            NativeSettingsFile(
                path, frozenset({_ENABLED_PLUGINS_KEY, _KNOWN_MARKETPLACES_KEY})
            ),
        )


def _marketplace_action(action: str) -> list[str]:
    return [
        CLAUDE_EXECUTABLE,
        _PLUGIN_COMMAND,
        "marketplace",
        action,
        MARKETPLACE_NAME,
    ]


def _plugin_id() -> str:
    return f"{CLAUDE_PLUGIN_NAME}@{MARKETPLACE_NAME}"


def _state_command(action: str, scope: str) -> list[str]:
    return [
        CLAUDE_EXECUTABLE,
        _PLUGIN_COMMAND,
        action,
        _plugin_id(),
        _SCOPE_FLAG,
        scope,
    ]


def _json_array(argv: list[str], cwd: Path) -> list[object]:
    completed = run_native_command(argv, cwd=cwd, platform=PLATFORM_CLAUDE)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise NativeCommandError(
            f"{shell_command(argv)} exited {completed.returncode}: {detail}"
        )
    try:
        parsed = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise NativeCommandError(
            f"{shell_command(argv)} returned invalid JSON: {exc}"
        ) from exc
    if not isinstance(parsed, list):
        raise NativeCommandError(f"{shell_command(argv)} did not return a JSON array")
    return cast(list[object], parsed)


def _marketplace_path(marketplace: dict[str, object]) -> str:
    path = marketplace.get(METADATA_PATH)
    if isinstance(path, str):
        return path
    source = marketplace.get(SOURCE_KEY)
    return source if isinstance(source, str) else "<missing marketplace path>"


def _registration(
    entry: dict[str, object],
    scope: str,
    layout: ClaudeLayout,
    cwd: Path,
) -> Registration:
    enabled = entry.get("projectEnabled") if scope == INSTALL_SCOPE_PROJECT else None
    if not isinstance(enabled, bool):
        enabled = _settings_enabled(layout, scope, cwd)
    raw_version = entry.get(VERSION_KEY)
    version = raw_version if isinstance(raw_version, str) else None
    raw_project = entry.get("projectPath")
    project = Path(raw_project) if isinstance(raw_project, str) else None
    return Registration(
        identity=_plugin_id(),
        scope=scope,
        version=version,
        enabled=enabled,
        project=project,
    )


def _settings_enabled(layout: ClaudeLayout, scope: str, cwd: Path) -> bool:
    path = (
        layout.project_settings(cwd)
        if scope == INSTALL_SCOPE_PROJECT
        else layout.user_settings()
    )
    if not path.exists():
        return True
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NativeCommandError(
            f"Cannot read Claude plugin enablement from {path}: {exc}"
        ) from exc
    if not isinstance(parsed, dict):
        raise NativeCommandError(
            f"Cannot read Claude plugin enablement from malformed settings: {path}"
        )
    settings = cast(dict[str, object], parsed)
    enabled_plugins = settings.get(_ENABLED_PLUGINS_KEY)
    if enabled_plugins is None:
        return True
    if not isinstance(enabled_plugins, dict):
        raise NativeCommandError(
            f"Cannot read Claude plugin enablement from malformed settings: {path}"
        )
    enabled = cast(dict[str, object], enabled_plugins).get(_plugin_id(), True)
    if not isinstance(enabled, bool):
        raise NativeCommandError(
            f"Cannot read Claude plugin enablement from malformed settings: {path}"
        )
    return enabled
