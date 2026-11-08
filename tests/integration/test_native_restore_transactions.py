"""Native staging and artifact snapshots restore committed filesystem state."""

from __future__ import annotations

from pathlib import Path

import pytest

from slopgate.installer.native.artifacts import restore_artifact
from slopgate.installer.native.packages import restore_staging
from tests.integration.native_restore_support import (
    mutate_artifact_again,
    observe_restore_case,
    prepare_restore_case,
)


def test_restore_staging_and_restore_artifact_recover_bytes_modes_and_absence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = prepare_restore_case(tmp_path, monkeypatch)
    staging_status = restore_staging(case.snapshot)
    mutate_artifact_again(case)
    restore_artifact(case.artifact, case.artifact_snapshot)
    restore_artifact(case.ghost, case.ghost_snapshot)
    observed = observe_restore_case(case, staging_status)

    assert observed == (
        0,
        case.expected_files,
        case.expected_mode,
        False,
        True,
    ), (
        "staging and artifact restoration must recover exact bytes/modes, remove "
        "new files, and restore currentness"
    )
