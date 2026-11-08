from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest

import slopgate.installer
import slopgate.installer.native.entry
from slopgate.constants import INSTALL_SCOPE_BOTH, INSTALL_SCOPE_USER
from slopgate.installer.native.commands import run_native_command
from tests.claude_installer_support import (
    ClaudeHarness,
    claude_harness,
    fake_state,
    settings_document,
)
from tests.native.claude_fake import PLUGIN_ID


@dataclass(frozen=True, slots=True)
class _ConfigScenario:
    harness: ClaudeHarness
    default_settings: Path
    default_bytes: bytes
    override_settings: Path
    override_original: dict[str, object]
    project_settings: Path
    project_original: dict[str, object]


def _settings_with_preserved_data(path: Path) -> dict[str, object]:
    return {
        "customSetting": {"retain": str(path)},
        "enabledPlugins": {"unrelated-plugin@other-market": True},
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [{"type": "command", "command": "keep-this-hook"}],
                }
            ]
        },
    }


def _prepare_scenario(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> _ConfigScenario:
    harness = claude_harness(tmp_path, monkeypatch)
    default_settings = harness.user_settings
    default_settings.parent.mkdir(parents=True)
    default_settings.write_text('{"defaultSetting":"untouched"}\n', encoding="utf-8")
    override_root = tmp_path / "alternate-claude-config"
    override_settings = override_root / "settings.json"
    override_settings.parent.mkdir(parents=True)
    override_settings.write_text(
        json.dumps(_settings_with_preserved_data(override_root), indent=2) + "\n",
        encoding="utf-8",
    )
    project_settings = harness.project_settings
    project_settings.parent.mkdir(parents=True)
    project_settings.write_text(
        json.dumps(_settings_with_preserved_data(harness.project), indent=2) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(override_root))
    return _ConfigScenario(
        harness,
        default_settings,
        default_settings.read_bytes(),
        override_settings,
        settings_document(override_settings),
        project_settings,
        settings_document(project_settings),
    )


def _plugin_for_scope(harness: ClaudeHarness, scope: str) -> dict[str, object]:
    plugins = cast(list[dict[str, object]], fake_state(harness)["plugins"])
    return next(plugin for plugin in plugins if plugin.get("scope") == scope)


def _install_and_disable_user(
    scenario: _ConfigScenario, monkeypatch: pytest.MonkeyPatch
) -> dict[str, object]:
    harness = scenario.harness
    monkeypatch.setattr(
        slopgate.installer.native.entry, "find_binary", lambda: "slopgate-initial"
    )
    status = slopgate.installer.install_claude(
        scope=INSTALL_SCOPE_BOTH, project_root=harness.project
    )
    if status != 0:
        raise AssertionError("initial Claude install should succeed")
    disabled = run_native_command(
        ["claude", "plugin", "disable", PLUGIN_ID, "--scope", INSTALL_SCOPE_USER],
        cwd=harness.project,
        platform="claude",
    )
    if disabled.returncode != 0:
        raise AssertionError("native Claude manager should disable user scope")
    return _plugin_for_scope(harness, INSTALL_SCOPE_USER)


def _preserves_unrelated_settings(
    current: dict[str, object], original: dict[str, object]
) -> bool:
    current_plugins = cast(dict[str, object], current.get("enabledPlugins", {}))
    original_plugins = cast(dict[str, object], original.get("enabledPlugins", {}))
    unrelated_key = "unrelated-plugin@other-market"
    return (
        current.get("hooks") == original.get("hooks")
        and current.get("customSetting") == original.get("customSetting")
        and current_plugins.get(unrelated_key) == original_plugins.get(unrelated_key)
    )


def _plugin_removed(current: dict[str, object]) -> bool:
    plugins = cast(dict[str, object], current.get("enabledPlugins", {}))
    return PLUGIN_ID not in plugins


def _override_lifecycle_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[int, bool, bool, bool, bool, bool, int, bool, bool, bool, bool]:
    scenario = _prepare_scenario(tmp_path, monkeypatch)
    prior = _install_and_disable_user(scenario, monkeypatch)
    monkeypatch.setattr(
        slopgate.installer.native.entry, "find_binary", lambda: "slopgate-refreshed"
    )
    refresh_status = slopgate.installer.install_claude(
        scope=INSTALL_SCOPE_BOTH, project_root=scenario.harness.project
    )
    refreshed = _plugin_for_scope(scenario.harness, INSTALL_SCOPE_USER)
    override_refresh = settings_document(scenario.override_settings)
    project_refresh = settings_document(scenario.project_settings)
    uninstall_status = slopgate.installer.uninstall_claude(
        scope=INSTALL_SCOPE_BOTH, project_root=scenario.harness.project
    )
    override_uninstall = settings_document(scenario.override_settings)
    project_uninstall = settings_document(scenario.project_settings)
    return (
        refresh_status,
        refreshed.get("version") != prior.get("version"),
        refreshed.get("enabled") is False,
        _preserves_unrelated_settings(override_refresh, scenario.override_original),
        _preserves_unrelated_settings(project_refresh, scenario.project_original),
        scenario.default_settings.read_bytes() == scenario.default_bytes,
        uninstall_status,
        _plugin_removed(override_uninstall),
        _preserves_unrelated_settings(override_uninstall, scenario.override_original),
        _preserves_unrelated_settings(project_uninstall, scenario.project_original),
        scenario.default_settings.read_bytes() == scenario.default_bytes,
    )


def test_claude_config_override_preserves_disabled_user_plugin_and_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed = _override_lifecycle_observation(tmp_path, monkeypatch)

    assert observed == (0, True, True, True, True, True, 0, True, True, True, True), (
        "override refresh and uninstall must preserve native disablement, unrelated "
        "settings/hooks, and the default profile"
    )
