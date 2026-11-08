from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from slopgate.constants import INSTALL_SCOPE_PROJECT, INSTALL_SCOPE_USER
from tests.native.pi_support import PiHarness, make_harness

USER_KEYS_DOCUMENT = '{\n  "theme": "dark",\n  "packages": []\n}\n'
FOREIGN_PACKAGE_DOCUMENT = '{"packages": ["../foreign"]}\n'


@dataclass(frozen=True, slots=True)
class _SettingsCase:
    scope: str
    seeded: str | None


@dataclass(frozen=True, slots=True)
class _Outcome:
    status: int
    settings_text: str | None
    directory_before: bool
    directory_after: bool


_CASES = (
    _SettingsCase(INSTALL_SCOPE_PROJECT, None),
    _SettingsCase(INSTALL_SCOPE_USER, None),
    _SettingsCase(INSTALL_SCOPE_PROJECT, USER_KEYS_DOCUMENT),
    _SettingsCase(INSTALL_SCOPE_USER, USER_KEYS_DOCUMENT),
    _SettingsCase(INSTALL_SCOPE_PROJECT, FOREIGN_PACKAGE_DOCUMENT),
)
_CASE_IDS = (
    "project-first-install",
    "user-first-install",
    "project-existing-settings",
    "user-existing-settings",
    "project-foreign-package",
)


def _settings_file(harness: PiHarness, scope: str) -> Path:
    if scope == INSTALL_SCOPE_PROJECT:
        return harness.project_settings
    return harness.user_settings


def _seed_settings(settings: Path, seeded: str | None) -> None:
    if seeded is None:
        return
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(seeded, encoding="utf-8")


def _failed_install_outcome(
    case: _SettingsCase, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> _Outcome:
    harness = make_harness(tmp_path, monkeypatch)
    settings = _settings_file(harness, case.scope)
    _seed_settings(settings, case.seeded)
    directory_before = settings.parent.exists()
    harness.fake.fail("install", case.scope, mutate_before_failure=True)
    status = harness.install(install_scope=case.scope)
    text = settings.read_text(encoding="utf-8") if settings.exists() else None
    return _Outcome(status, text, directory_before, settings.parent.exists())


@pytest.mark.parametrize("case", _CASES, ids=_CASE_IDS)
def test_failed_install_returns_native_settings_to_their_prior_state(
    case: _SettingsCase,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    outcome = _failed_install_outcome(case, tmp_path, monkeypatch)

    assert outcome.status == 1, "an install failing after registration must fail"
    assert outcome.settings_text == case.seeded, (
        "rollback must restore the settings file Pi rewrote, or remove the one it created"
    )
    assert outcome.directory_after is outcome.directory_before, (
        "a settings directory created by the failed install must not be left behind"
    )
