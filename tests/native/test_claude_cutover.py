"""Claude cutover rollback must restore both scopes after a later failure."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.native.claude_cutover_support import project_cutover_failure_observation


def test_project_cutover_failure_restores_user_hooks_and_native_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed = project_cutover_failure_observation(tmp_path, monkeypatch)

    assert (
        observed.status,
        observed.user_remove_statuses,
        observed.failure_observations,
        observed.user_hooks_restored,
        observed.user_unrelated_preserved,
        observed.user_mode_restored,
        observed.project_settings_restored,
        observed.project_document_restored,
        observed.native_state_restored,
        observed.staging_restored,
    ) == (
        1,
        (0,),
        ((True, True, True, True),),
        True,
        True,
        True,
        True,
        True,
        True,
        True,
    ), (
        "later project cutover failure must occur after user hooks are removed and "
        "restore original files, unrelated settings, staging, and native state"
    )
