"""PiCutover observes and restores recognized prior extension artifacts."""

from __future__ import annotations

from pathlib import Path

import pytest

from slopgate.constants import INSTALL_SCOPE_USER
from slopgate.installer.native.model import NativeRequest
from slopgate.installer.native.pi.cutover import PiCutover
from tests.native.cutover_behavior_support import (
    exercise_pi_cutover,
    seed_pi_cutover_case,
)


def test_pi_cutover_describes_retires_and_restores_owned_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = seed_pi_cutover_case(tmp_path, monkeypatch)
    request = NativeRequest(False, (INSTALL_SCOPE_USER,), case.harness.project)
    cutover = PiCutover(request)
    observed = exercise_pi_cutover(cutover, case)

    assert observed.describes_every_owned_file, (
        "PiCutover.describe must list each recognized prior package artifact"
    )
    assert (observed.remove_status, observed.owned_files_retired) == (0, True), (
        "PiCutover.remove must retire owned files without deleting unrelated siblings"
    )
    assert observed.sibling_unchanged_after_remove, (
        "PiCutover.remove must leave unrelated package siblings byte-identical"
    )
    assert (observed.restore_status, observed.owned_files_restored) == (0, True), (
        "PiCutover.restore must restore the exact saved bytes and modes"
    )
    assert observed.sibling_unchanged_after_restore, (
        "restoring owned artifacts must not change the unrelated sibling"
    )
