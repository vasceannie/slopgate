"""Claude native commands and host identity retain their concrete contracts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from slopgate.constants import (
    INSTALL_SCOPE_PROJECT,
    INSTALL_SCOPE_USER,
    PLATFORM_CLAUDE,
)
from slopgate.installer.native.claude import (
    CLAUDE_PLUGIN_NAME,
    ClaudeCommands,
    ClaudeHost,
    ClaudeLayout,
)
from slopgate.installer.native.model import Registration
from slopgate.installer.native.packages import MARKETPLACE_NAME


def _render_payload(binary: str, version: str) -> dict[str, str]:
    return {"hooks.json": json.dumps({"binary": binary, "version": version})}


def _command_argv_observation(
    commands: ClaudeCommands, scope: str
) -> tuple[object, ...]:
    entry_root = Path("/sandbox/native/claude/marketplace")
    identity = f"{CLAUDE_PLUGIN_NAME}@{MARKETPLACE_NAME}"
    disabled_registration = Registration(identity, scope, "1.0.0", False)
    return (
        commands.marketplace_add(entry_root),
        commands.install(scope, None),
        commands.install(scope, disabled_registration),
        commands.uninstall(scope),
    )


def _expected_command_argv(scope: str) -> tuple[object, ...]:
    identity = f"{CLAUDE_PLUGIN_NAME}@{MARKETPLACE_NAME}"
    install_argv = ["claude", "plugin", "install", identity, "--scope", scope]
    return (
        [
            "claude",
            "plugin",
            "marketplace",
            "add",
            "./marketplace",
        ],
        [install_argv],
        [
            install_argv,
            ["claude", "plugin", "disable", identity, "--scope", scope],
        ],
        [
            "claude",
            "plugin",
            "uninstall",
            identity,
            "--scope",
            scope,
            "--keep-data",
        ],
    )


@pytest.mark.parametrize("scope", (INSTALL_SCOPE_USER, INSTALL_SCOPE_PROJECT))
def test_claude_commands_build_scoped_marketplace_plugin_and_disable_argv(
    scope: str,
) -> None:
    assert _command_argv_observation(ClaudeCommands(), scope) == (
        _expected_command_argv(scope)
    ), (
        "ClaudeCommands must preserve marketplace path, selected scope, disabled "
        "state, and marketplace data"
    )


def test_claude_marketplace_add_runs_from_staged_parent_so_relative_source_resolves() -> (
    None
):
    entry_root = Path("/sandbox/native/claude/marketplace")
    commands = ClaudeCommands()
    assert commands.marketplace_add_cwd(entry_root, Path("/project")) == (
        entry_root.parent
    ), "Claude add uses a ./relative source, so cwd must be the marketplace parent"


def _claude_layout() -> ClaudeLayout:
    return ClaudeLayout(
        user_settings=lambda: Path("/sandbox/.claude/settings.json"),
        project_settings=lambda root: root / ".claude" / "settings.json",
        user_root=lambda: Path("/sandbox/.claude"),
        render_payload=_render_payload,
    )


def _host_behavior_observation(host: ClaudeHost) -> tuple[bool, bool, bool]:
    first_plan = host.build_plan("slopgate --config /sandbox/config.toml")
    repeated_plan = host.build_plan("slopgate --config /sandbox/config.toml")
    changed_plan = host.build_plan("slopgate --config /different/config.toml")
    plugin_uninstall = host.commands.uninstall(INSTALL_SCOPE_USER)
    return (
        (
            host.platform,
            host.plugin_name,
            plugin_uninstall[3],
        )
        == (
            PLATFORM_CLAUDE,
            CLAUDE_PLUGIN_NAME,
            f"{CLAUDE_PLUGIN_NAME}@{MARKETPLACE_NAME}",
        ),
        (first_plan.version, first_plan.package_dir)
        == (repeated_plan.version, repeated_plan.package_dir),
        first_plan.version != changed_plan.version,
    )


def test_claude_host_keeps_plugin_identity_and_plan_version_stable() -> None:
    host = ClaudeHost(_claude_layout())
    observed = _host_behavior_observation(host)

    assert observed == (True, True, True), (
        "ClaudeHost must preserve plugin identity and stable versioned plans while "
        "changing payload inputs"
    )
