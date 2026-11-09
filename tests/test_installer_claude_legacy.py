"""Tests for scope-safe Claude legacy hook rollback and native cutover."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from pytest import MonkeyPatch
from slopgate._types import object_dict, object_list
from slopgate.constants import INSTALL_SCOPE_USER
from slopgate.installer.native.claude import ClaudeLayout
from slopgate.installer.native.claude_legacy import ClaudeLegacyCutover
from slopgate.installer.native.model import make_request
import slopgate
import slopgate.installer.native.entry
from tests.claude_installer_support import (
    ClaudeHarness,
    assert_legacy_removed,
    claude_harness as _base_claude_harness,
    fake_state,
    seed_legacy_settings,
)
from tests.native.claude_fake import MARKETPLACE_NAME, PLUGIN_ID


def _settings(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def _hooks(settings: dict[str, object]) -> dict[str, object]:
    return cast(dict[str, object], settings["hooks"])


def _plugins(state: dict[str, object]) -> list[dict[str, object]]:
    return [object_dict(item) for item in object_list(state.get("plugins"))]


def _plugin_for_scope(state: dict[str, object], scope: str) -> dict[str, object]:
    selected = [item for item in _plugins(state) if item.get("scope") == scope]
    if len(selected) != 1:
        raise AssertionError(
            f"Expected one {scope} registration, found {len(selected)}"
        )
    return selected[0]


def _native_claude_harness(tmp_path: Path, monkeypatch: MonkeyPatch) -> ClaudeHarness:
    harness = _base_claude_harness(tmp_path, monkeypatch)
    monkeypatch.setattr(
        slopgate.installer.native.entry, "find_binary", lambda: "slopgate"
    )
    return harness


def _install_both(harness: ClaudeHarness) -> dict[str, object]:
    status = slopgate.installer.install_claude(
        scope="both", project_root=harness.project
    )
    assert status == 0, (
        "both-scope installation should succeed through Claude's plugin manager"
    )
    return fake_state(harness)


def _settings_bytes(harness: ClaudeHarness) -> tuple[bytes, bytes]:
    return (
        harness.user_settings.read_bytes(),
        harness.project_settings.read_bytes(),
    )


def _install_without_cli(harness: ClaudeHarness, monkeypatch: MonkeyPatch) -> int:
    monkeypatch.setenv("PATH", "")
    return slopgate.installer.install_claude(scope="both", project_root=harness.project)


def _seed_foreign_marketplace(
    harness: ClaudeHarness, tmp_path: Path
) -> tuple[str, bytes]:
    foreign_path = str(tmp_path / "foreign-marketplace")
    harness.state_path.write_text(
        json.dumps(
            {"marketplaces": {MARKETPLACE_NAME: {"path": foreign_path}}, "plugins": []}
        ),
        encoding="utf-8",
    )
    return foreign_path, harness.user_settings.read_bytes()


def _add_native_mutations(path: Path) -> None:
    settings = _settings(path)
    enabled = cast(dict[str, object], settings["enabledPlugins"])
    enabled["native-plugin@market"] = True
    hooks = cast(dict[str, object], settings["hooks"])
    hooks["PostToolUse"] = [
        {"hooks": [{"type": "command", "command": "added-after-cutover"}]}
    ]
    path.write_text(json.dumps(settings), encoding="utf-8")


def _assert_restored_hook_groups(hooks: dict[str, object]) -> None:
    pre_tool_use = cast(list[object], hooks["PreToolUse"])
    groups = [cast(dict[str, object], item) for item in pre_tool_use]
    owned_groups = [
        group
        for group in groups
        if any(
            isinstance(text := command.get("command"), str)
            and "slopgate handle" in text
            for command in cast(list[dict[str, object]], group["hooks"])
        )
    ]
    assert len(owned_groups) == 1, "the original owned group should be restored"
    owned_group = owned_groups[0]
    assert owned_group.get("matcher") == "Bash", (
        "rollback must restore matcher metadata"
    )
    assert owned_group.get("legacyGroup") == "preserve-on-rollback", (
        "rollback must restore original owned-group metadata"
    )
    command_values = {
        command.get("command")
        for group in groups
        for command in cast(list[dict[str, object]], group["hooks"])
    }
    assert command_values == {
        "slopgate handle --platform claude",
        "other-gate",
    }, "rollback must restore owned hooks and preserve unrelated commands"


def _prepared_cutover(harness: ClaudeHarness) -> ClaudeLegacyCutover:
    seed_legacy_settings(harness)
    layout = ClaudeLayout(
        user_settings=lambda: harness.user_settings,
        project_settings=lambda _root: harness.project_settings,
        user_root=lambda: harness.home / ".claude",
        render_payload=lambda _binary, _version: {},
    )
    request = make_request(INSTALL_SCOPE_USER, harness.project, dry_run=False)
    cutover = ClaudeLegacyCutover(request, layout)
    cutover.preflight()
    cutover.capture()
    assert cutover.remove(INSTALL_SCOPE_USER) == 0, "legacy hooks should be removable"
    _add_native_mutations(harness.user_settings)
    return cutover


def test_claude_install_registers_native_plugin_and_migrates_both_scopes(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    harness = _native_claude_harness(tmp_path, monkeypatch)
    originals = seed_legacy_settings(harness)
    state = _install_both(harness)
    registrations = _plugins(state)
    assert len(registrations) == 2, (
        "native inventory should contain user and project registrations"
    )
    assert {item["id"] for item in registrations} == {PLUGIN_ID}, (
        "native plugin identity must be exact"
    )
    assert {item["scope"] for item in registrations} == {"user", "project"}, (
        "both requested scopes must be registered"
    )
    project_registration = _plugin_for_scope(state, "project")
    assert project_registration["projectPath"] == str(harness.project.resolve()), (
        "project registration must target the requested root"
    )
    assert_legacy_removed(harness.user_settings, originals[0])
    assert_legacy_removed(harness.project_settings, originals[1])


def test_claude_missing_cli_fails_without_cutting_over_legacy_hooks(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    harness = _native_claude_harness(tmp_path, monkeypatch)
    seed_legacy_settings(harness)
    original = _settings_bytes(harness)
    status = _install_without_cli(harness, monkeypatch)
    assert status == 1, "native install must fail when Claude is unavailable"
    assert _settings_bytes(harness) == original, (
        "missing CLI must leave legacy hooks intact"
    )
    assert not harness.state_path.exists(), (
        "missing CLI must not create native registration state"
    )


def test_claude_foreign_marketplace_collision_is_refused(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    harness = _native_claude_harness(tmp_path, monkeypatch)
    seed_legacy_settings(harness)
    foreign_path, original = _seed_foreign_marketplace(harness, tmp_path)
    status = slopgate.installer.install_claude(project_root=harness.project)
    assert status == 1, "a foreign marketplace source must not be replaced"
    assert harness.user_settings.read_bytes() == original, (
        "collision refusal must preserve legacy config"
    )
    assert fake_state(harness) == {
        "marketplaces": {MARKETPLACE_NAME: {"path": foreign_path}},
        "plugins": [],
    }, "foreign marketplace source must remain unchanged"


def test_restore_merges_owned_hooks_without_reverting_native_settings(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    harness = _native_claude_harness(tmp_path, monkeypatch)
    cutover = _prepared_cutover(harness)
    assert cutover.restore() == 0, "owned hook groups should restore cleanly"
    restored = _settings(harness.user_settings)
    hooks = _hooks(restored)
    assert restored["enabledPlugins"] == {
        "unrelated-plugin@other-market": True,
        "native-plugin@market": True,
    }, "rollback must retain native enabledPlugins mutations"
    assert "PostToolUse" in hooks, (
        "rollback must retain unrelated hooks added after cutover"
    )
    _assert_restored_hook_groups(hooks)
