"""Composed observations for Claude native rollback scenarios."""

from __future__ import annotations

import json
import stat
from dataclasses import dataclass
from pathlib import Path

import pytest

import slopgate.installer
import slopgate.installer.native.entry
from slopgate._types import object_dict, object_list
from slopgate.constants import INSTALL_SCOPE_BOTH, INSTALL_SCOPE_PROJECT
from slopgate.installer.native.claude_legacy import ClaudeLegacyCutover
from slopgate.installer.native.migration import extract_owned_hooks
from tests.claude_installer_support import (
    ClaudeHarness,
    claude_harness,
    fake_state,
    seed_legacy_settings,
    settings_document,
    tree_digest,
)

ROLLBACK_SETTING_MODE = 0o600


@dataclass(frozen=True, slots=True)
class CutoverFailureObservation:
    status: int
    user_remove_statuses: tuple[int, ...]
    failure_observations: tuple[tuple[bool, bool, bool, bool], ...]
    user_hooks_restored: bool
    user_unrelated_preserved: bool
    user_mode_restored: bool
    project_settings_restored: bool
    project_document_restored: bool
    native_state_restored: bool
    staging_restored: bool


def plugins(state: dict[str, object]) -> list[dict[str, object]]:
    """Normalize fake Claude plugin entries from the recorded manager state."""
    return [object_dict(item) for item in object_list(state.get("plugins"))]


def plugin_for_scope(state: dict[str, object], scope: str) -> dict[str, object]:
    """Return the unique registered Slopgate plugin for one scope."""
    selected = [item for item in plugins(state) if item.get("scope") == scope]
    if len(selected) != 1:
        raise AssertionError(
            f"Expected one {scope} registration, found {len(selected)}"
        )
    return selected[0]


def native_claude_harness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> ClaudeHarness:
    """Build the isolated Claude manager and bind binary discovery to the fixture."""
    harness = claude_harness(tmp_path, monkeypatch)
    monkeypatch.setattr(
        slopgate.installer.native.entry, "find_binary", lambda: "slopgate"
    )
    return harness


def setting_snapshot(path: Path) -> tuple[bytes, int]:
    """Capture a settings file's bytes and supported mode bits."""
    return path.read_bytes(), stat.S_IMODE(path.stat().st_mode)


def _user_cutover_failure_observation(
    path: Path, original: dict[str, object]
) -> tuple[bool, bool, bool, bool]:
    current = settings_document(path)
    hooks = json.dumps(current.get("hooks"))
    return (
        not extract_owned_hooks(current.get("hooks")),
        current.get("customSetting") == original.get("customSetting"),
        "other-gate" in hooks,
        "unrelated-stop-hook" in hooks,
    )


def _install_with_project_failure(
    harness: ClaudeHarness,
    monkeypatch: pytest.MonkeyPatch,
    original_user: dict[str, object],
) -> tuple[int, tuple[int, ...], tuple[tuple[bool, bool, bool, bool], ...]]:
    user_remove_statuses: list[int] = []
    failure_observations: list[tuple[bool, bool, bool, bool]] = []
    original_remove = ClaudeLegacyCutover.remove

    def fail_project_removal(cutover: ClaudeLegacyCutover, scope: str) -> int:
        if scope == INSTALL_SCOPE_PROJECT:
            failure_observations.append(
                _user_cutover_failure_observation(harness.user_settings, original_user)
            )
            return 1
        status = original_remove(cutover, scope)
        user_remove_statuses.append(status)
        return status

    monkeypatch.setattr(ClaudeLegacyCutover, "remove", fail_project_removal)
    status = slopgate.installer.install_claude(
        scope=INSTALL_SCOPE_BOTH, project_root=harness.project
    )
    return status, tuple(user_remove_statuses), tuple(failure_observations)


def project_cutover_failure_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> CutoverFailureObservation:
    """Fail project cutover after user removal and record complete compensation."""
    harness = native_claude_harness(tmp_path, monkeypatch)
    original_user, original_project = seed_legacy_settings(harness)
    harness.user_settings.chmod(ROLLBACK_SETTING_MODE)
    harness.project_settings.chmod(ROLLBACK_SETTING_MODE)
    user_before = setting_snapshot(harness.user_settings)
    project_before = setting_snapshot(harness.project_settings)
    staging_before = tree_digest((harness.staging_root,))
    status, removed, observed_during_failure = _install_with_project_failure(
        harness, monkeypatch, original_user
    )
    user_after = settings_document(harness.user_settings)
    project_after = settings_document(harness.project_settings)
    state = fake_state(harness)
    user_hooks = json.dumps(user_after.get("hooks"))
    return CutoverFailureObservation(
        status,
        removed,
        observed_during_failure,
        extract_owned_hooks(user_after.get("hooks"))
        == extract_owned_hooks(original_user.get("hooks")),
        user_after.get("customSetting") == original_user.get("customSetting")
        and user_after.get("enabledPlugins") == original_user.get("enabledPlugins")
        and "other-gate" in user_hooks
        and "unrelated-stop-hook" in user_hooks,
        setting_snapshot(harness.user_settings)[1] == user_before[1],
        setting_snapshot(harness.project_settings) == project_before,
        project_after == original_project,
        (state.get("plugins"), state.get("marketplaces")) == ([], {}),
        tree_digest((harness.staging_root,)) == staging_before,
    )
