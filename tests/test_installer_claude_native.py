"""End-to-end contract tests for Claude's native plugin installation."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from pytest import CaptureFixture, MonkeyPatch

import slopgate
import slopgate.installer
import slopgate.installer.native.entry
from slopgate._types import object_list
from tests.claude_installer_support import (
    ClaudeHarness,
    assert_settings_rollback_preserved,
    catalog_plugin,
    fake_calls,
    fake_state,
    mutating_calls,
    seed_legacy_settings,
    settings_document,
    tree_digest,
)
from tests.native.claude_cutover_support import (
    native_claude_harness as _native_claude_harness,
    plugin_for_scope as _plugin_for_scope,
    plugins as _plugins,
)
from tests.native.claude_fake import PLUGIN_ID
from tests.native.commands import would_run_prefix


def _repeat_both_install(
    harness: ClaudeHarness,
) -> tuple[dict[str, object], str, list[list[str]]]:
    assert (
        slopgate.installer.install_claude(scope="both", project_root=harness.project)
        == 0
    ), "repeat native installation should succeed"
    return (
        fake_state(harness),
        tree_digest((harness.staging_root,)),
        mutating_calls(fake_calls(harness)),
    )


def _malformed_settings_harness(
    tmp_path: Path, monkeypatch: MonkeyPatch, document: str
) -> tuple[ClaudeHarness, bytes]:
    harness = _native_claude_harness(tmp_path, monkeypatch)
    harness.user_settings.parent.mkdir(parents=True)
    harness.user_settings.write_text(document, encoding="utf-8")
    return harness, harness.user_settings.read_bytes()


def _failed_second_scope(
    harness: ClaudeHarness, monkeypatch: MonkeyPatch
) -> tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
    assert slopgate.installer.install_claude(project_root=harness.project) == 0, (
        "prior user plugin registration should exist"
    )
    original_user, original_project = seed_legacy_settings(harness)
    old_user = _plugin_for_scope(fake_state(harness), "user")
    monkeypatch.setattr(
        slopgate.installer.native.entry,
        "find_binary",
        lambda: "changed slopgate binary",
    )
    monkeypatch.setenv("FAKE_CLAUDE_FAIL", "install:project")
    monkeypatch.setenv("FAKE_CLAUDE_FAIL_AFTER", "1")
    status = slopgate.installer.install_claude(
        scope="both", project_root=harness.project
    )
    assert status == 1, (
        "injected project registration failure must abort the transaction"
    )
    return old_user, original_user, original_project, fake_state(harness)


def _replace_after_disabled_user(
    harness: ClaudeHarness, monkeypatch: MonkeyPatch
) -> dict[str, object]:
    assert (
        slopgate.installer.install_claude(scope="both", project_root=harness.project)
        == 0
    ), "both native scopes should install"
    command = [
        shutil.which("claude") or "claude",
        "plugin",
        "disable",
        PLUGIN_ID,
        "--scope",
        "user",
    ]
    result = subprocess.run(
        command, cwd=harness.project, check=False, capture_output=True, text=True
    )
    assert result.returncode == 0, "native disable command should record the state"
    state = fake_state(harness)
    state["plugins"] = [
        {**entry, "enabled": True, "projectEnabled": True} for entry in _plugins(state)
    ]
    harness.state_path.write_text(json.dumps(state), encoding="utf-8")
    monkeypatch.setattr(
        slopgate.installer.native.entry,
        "find_binary",
        lambda: "new slopgate invocation",
    )
    assert (
        slopgate.installer.install_claude(scope="both", project_root=harness.project)
        == 0
    ), "native replacement should succeed"
    return state


def _dry_run_observation(
    harness: ClaudeHarness, capsys: CaptureFixture[str]
) -> tuple[int, str, str, str, list[list[str]]]:
    before = tree_digest((harness.home, harness.project))
    status = slopgate.installer.install_claude(
        dry_run=True, scope="both", project_root=harness.project
    )
    output = capsys.readouterr().out
    after = tree_digest((harness.home, harness.project))
    return status, output, before, after, mutating_calls(fake_calls(harness))


def _uninstall_project_scope(harness: ClaudeHarness) -> dict[str, object]:
    assert (
        slopgate.installer.install_claude(scope="both", project_root=harness.project)
        == 0
    ), "both native scopes should install"
    state = fake_state(harness)
    plugins = object_list(state.get("plugins"))
    plugins.append(
        {"id": "unrelated@other", "version": "1", "scope": "user", "enabled": True}
    )
    state["plugins"] = plugins
    harness.state_path.write_text(json.dumps(state), encoding="utf-8")
    status = slopgate.installer.uninstall_claude(
        scope="project", project_root=harness.project
    )
    assert status == 0, "project-only uninstall should succeed"
    return fake_state(harness)


def _version_upgrade(
    harness: ClaudeHarness, monkeypatch: MonkeyPatch
) -> tuple[Path, dict[str, object], Path, bytes, dict[str, object]]:
    assert slopgate.installer.install_claude(project_root=harness.project) == 0, (
        "initial package registration should succeed"
    )
    catalog_path = (
        harness.staging_root / "marketplace" / ".claude-plugin" / "marketplace.json"
    )
    old_entry, old_root = catalog_plugin(catalog_path)
    old_hooks = (old_root / "hooks" / "hooks.json").read_bytes()
    old_manifest = settings_document(old_root / ".claude-plugin" / "plugin.json")
    assert old_entry.get("version") == old_manifest.get("version"), (
        "catalog and plugin manifest versions must match"
    )
    monkeypatch.setattr(slopgate, "__version__", "99.0.0")
    assert slopgate.installer.install_claude(project_root=harness.project) == 0, (
        "version-only upgrade should register the new snapshot"
    )
    new_entry, new_root = catalog_plugin(catalog_path)
    new_manifest = settings_document(new_root / ".claude-plugin" / "plugin.json")
    return old_root, new_entry, new_root, old_hooks, new_manifest


def test_claude_install_is_idempotent_for_current_native_versions(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    harness = _native_claude_harness(tmp_path, monkeypatch)
    assert (
        slopgate.installer.install_claude(scope="both", project_root=harness.project)
        == 0
    ), "initial native installation should succeed"
    previous_state = fake_state(harness)
    previous_stage = tree_digest((harness.staging_root,))
    harness.log_path.write_text("", encoding="utf-8")
    state, stage, mutations = _repeat_both_install(harness)
    assert state == previous_state, "idempotent install must preserve native inventory"
    assert stage == previous_stage, "idempotent install must reuse staged content"
    assert mutations == [], "current registrations must not be reinstalled"


@pytest.mark.parametrize("document", ["{not-json", "[]", '{"hooks": []}'])
def test_claude_malformed_settings_block_native_install(
    tmp_path: Path, monkeypatch: MonkeyPatch, document: str
) -> None:
    harness, original = _malformed_settings_harness(tmp_path, monkeypatch, document)
    status = slopgate.installer.install_claude(project_root=harness.project)
    assert status == 1, "malformed settings must refuse the native cutover"
    assert harness.user_settings.read_bytes() == original, (
        "malformed settings must remain byte-identical"
    )
    assert not harness.state_path.exists(), (
        "malformed settings must block native state changes"
    )


def test_claude_second_scope_failure_restores_prior_registration_and_settings(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    harness = _native_claude_harness(tmp_path, monkeypatch)
    old_user, original_user, original_project, current_state = _failed_second_scope(
        harness, monkeypatch
    )
    current_user = _plugin_for_scope(current_state, "user")
    assert current_user["version"] == old_user["version"], (
        "rollback must restore the prior user registration"
    )
    assert not any(
        item["scope"] == "project" and item["id"] == PLUGIN_ID
        for item in _plugins(current_state)
    ), "failed project registration must be removed"
    assert_settings_rollback_preserved(harness.user_settings, original_user)
    assert_settings_rollback_preserved(harness.project_settings, original_project)


def test_claude_replacement_restores_native_disabled_state(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    harness = _native_claude_harness(tmp_path, monkeypatch)
    previous_state = _replace_after_disabled_user(harness, monkeypatch)
    previous = _plugin_for_scope(previous_state, "user")
    refreshed = _plugin_for_scope(fake_state(harness), "user")
    assert refreshed["version"] != previous["version"], (
        "changed invocation must replace the payload"
    )
    assert refreshed["enabled"] is False, (
        "replacement must preserve the disabled user scope despite effective project enablement"
    )


def test_claude_replacement_preserves_enabled_project_scope(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    harness = _native_claude_harness(tmp_path, monkeypatch)
    _replace_after_disabled_user(harness, monkeypatch)
    project_registration = _plugin_for_scope(fake_state(harness), "project")
    assert (
        project_registration["id"],
        project_registration["scope"],
        project_registration["enabled"],
        project_registration["projectPath"],
    ) == (
        PLUGIN_ID,
        "project",
        True,
        str(harness.project.resolve()),
    ), "refresh must preserve the enabled project scope"
    assert settings_document(harness.project_settings)["enabledPlugins"] == {
        PLUGIN_ID: True
    }, "enabled project scope must persist in native settings"


def test_claude_dry_run_does_not_mutate_files_or_native_state(
    tmp_path: Path, monkeypatch: MonkeyPatch, capsys: CaptureFixture[str]
) -> None:
    harness = _native_claude_harness(tmp_path, monkeypatch)
    seed_legacy_settings(harness)
    status, output, before, after, mutations = _dry_run_observation(harness, capsys)
    assert status == 0, "native dry-run preflight should succeed"
    assert would_run_prefix("claude", "plugin", "marketplace", "add") in output, (
        "dry-run should describe marketplace registration"
    )
    assert would_run_prefix("claude", "plugin", "install") in output, (
        "dry-run should describe scoped plugin registration"
    )
    assert after == before, (
        "dry-run must leave settings, staging, and directories unchanged"
    )
    assert mutations == [], "dry-run must not invoke native mutations"
    assert not harness.state_path.exists(), (
        "read-only inventory calls must not persist fake native state"
    )


def test_claude_selected_project_uninstall_keeps_user_registration_and_other_plugins(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    harness = _native_claude_harness(tmp_path, monkeypatch)
    state = _uninstall_project_scope(harness)
    entries = _plugins(state)
    assert any(
        item["id"] == PLUGIN_ID and item["scope"] == "user" for item in entries
    ), "user registration must remain"
    assert any(item["id"] == "unrelated@other" for item in entries), (
        "unrelated native plugins must remain"
    )
    assert not any(
        item["id"] == PLUGIN_ID and item["scope"] == "project" for item in entries
    ), "selected project registration must be removed"


def test_claude_version_upgrade_creates_snapshot_and_keeps_versions_consistent(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    harness = _native_claude_harness(tmp_path, monkeypatch)
    old_root, new_entry, new_root, old_hooks, new_manifest = _version_upgrade(
        harness, monkeypatch
    )
    assert new_root != old_root, (
        "version-only upgrade must create a new immutable snapshot"
    )
    assert new_entry["version"] == new_manifest["version"], (
        "upgraded catalog and manifest versions must match"
    )
    assert (new_root / "hooks" / "hooks.json").read_bytes() == old_hooks, (
        "same invocation must render identical hook bodies"
    )
