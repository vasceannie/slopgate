from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

import slopgate.installer
from slopgate.constants import INSTALL_SCOPE_PROJECT, INSTALL_SCOPE_USER
from tests.claude_installer_support import ClaudeHarness, fake_calls, mutating_calls
from tests.native.claude_cutover_support import native_claude_harness

SEEDED_SETTINGS = '{\n  "model": "opus"\n}\n'


@dataclass(frozen=True, slots=True)
class _SettingsCase:
    scope: str
    seed: str | None
    failing_command: str


_INSTALL_PROJECT = f"install:{INSTALL_SCOPE_PROJECT}"
_INSTALL_USER = f"install:{INSTALL_SCOPE_USER}"
_MARKETPLACE_ADD = "marketplace:add"
_CASES = (
    _SettingsCase(INSTALL_SCOPE_PROJECT, None, _INSTALL_PROJECT),
    _SettingsCase(INSTALL_SCOPE_USER, None, _INSTALL_USER),
    _SettingsCase(INSTALL_SCOPE_PROJECT, SEEDED_SETTINGS, _INSTALL_PROJECT),
    _SettingsCase(INSTALL_SCOPE_USER, SEEDED_SETTINGS, _INSTALL_USER),
    _SettingsCase(INSTALL_SCOPE_PROJECT, None, _MARKETPLACE_ADD),
    _SettingsCase(INSTALL_SCOPE_PROJECT, SEEDED_SETTINGS, _MARKETPLACE_ADD),
)
_CASE_IDS = (
    "project-first-install",
    "user-first-install",
    "project-existing-settings",
    "user-existing-settings",
    "marketplace-add-fails-first-install",
    "marketplace-add-fails-existing-settings",
)


def _seed(harness: ClaudeHarness, seed: str | None) -> None:
    if seed is None:
        return
    for path in (harness.project_settings, harness.user_settings):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(seed, encoding="utf-8")


def _state(harness: ClaudeHarness) -> tuple[object, ...]:
    """Settings text (or None) and settings-directory existence for both scopes."""
    files = (harness.project_settings, harness.user_settings)
    texts = tuple(
        path.read_text(encoding="utf-8") if path.exists() else None for path in files
    )
    return (*texts, *(path.parent.exists() for path in files))


def _failed_install(
    case: _SettingsCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[int, tuple[object, ...], tuple[object, ...]]:
    harness = native_claude_harness(tmp_path, monkeypatch)
    _seed(harness, case.seed)
    before = _state(harness)
    monkeypatch.setenv("FAKE_CLAUDE_FAIL", case.failing_command)
    monkeypatch.setenv("FAKE_CLAUDE_FAIL_AFTER", "1")
    status = slopgate.installer.install_claude(
        scope=case.scope, project_root=harness.project
    )
    return status, before, _state(harness)


@pytest.mark.parametrize("case", _CASES, ids=_CASE_IDS)
def test_failed_install_returns_claude_settings_to_their_prior_state(
    case: _SettingsCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    status, before, after = _failed_install(case, tmp_path, monkeypatch)

    assert status == 1, "an install failing after registration must fail"
    assert after == before, (
        "rollback must restore every Claude settings file and remove the files "
        "and directories the failed install created, including the user settings "
        "that recording the marketplace created"
    )


@pytest.mark.parametrize(
    ("fail_after", "removal_expected"),
    (("", False), ("1", True)),
    ids=("rejected-add-registers-nothing", "add-fails-after-registering"),
)
def test_failed_marketplace_add_removes_only_a_registration_that_landed(
    fail_after: str,
    removal_expected: bool,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    harness = native_claude_harness(tmp_path, monkeypatch)
    monkeypatch.setenv("FAKE_CLAUDE_FAIL", _MARKETPLACE_ADD)
    monkeypatch.setenv("FAKE_CLAUDE_FAIL_AFTER", fail_after)

    status = slopgate.installer.install_claude(
        scope=INSTALL_SCOPE_USER, project_root=harness.project
    )

    mutations = [call[1:3] for call in mutating_calls(fake_calls(harness))]
    assert status == 1, "a failed marketplace add must fail the install"
    assert (["marketplace", "remove"] in mutations) is removal_expected, (
        "rollback must remove the marketplace only when the add actually registered it"
    )
