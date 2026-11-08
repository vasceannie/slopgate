"""Seed and observe Pi pre-native package cutover behavior."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from slopgate.constants import INSTALL_SCOPE_USER
from slopgate.installer.native.pi.cutover import PiCutover
from tests.native.pi_support import (
    PiHarness,
    legacy_paths,
    make_harness,
    original_artifacts_match,
    seed_legacy,
)


@dataclass(frozen=True, slots=True)
class PiCutoverCase:
    harness: PiHarness
    seed: dict[Path, tuple[bytes, int]]
    keep_path: Path
    keep_bytes: bytes


@dataclass(frozen=True, slots=True)
class PiCutoverObservation:
    describes_every_owned_file: bool
    remove_status: int
    owned_files_retired: bool
    sibling_unchanged_after_remove: bool
    restore_status: int
    owned_files_restored: bool
    sibling_unchanged_after_restore: bool


def seed_pi_cutover_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> PiCutoverCase:
    """Build owned user-scope artifacts plus a byte-stable unrelated sibling."""
    harness = make_harness(tmp_path, monkeypatch)
    seed = seed_legacy(harness, INSTALL_SCOPE_USER)
    keep_path = legacy_paths(harness, INSTALL_SCOPE_USER)[0].parent / "keep.txt"
    return PiCutoverCase(harness, seed, keep_path, keep_path.read_bytes())


def exercise_pi_cutover(
    cutover: PiCutover, case: PiCutoverCase
) -> PiCutoverObservation:
    """Run preflight, capture, removal and restore, retaining each observed result."""
    descriptions = cutover.describe()
    cutover.preflight()
    cutover.capture()
    remove_status = cutover.remove(INSTALL_SCOPE_USER)
    retired = all(not path.exists() for path in case.seed)
    sibling_during_remove = case.keep_path.read_bytes() == case.keep_bytes
    restore_status = cutover.restore()
    return PiCutoverObservation(
        all(any(str(path) in line for line in descriptions) for path in case.seed),
        remove_status,
        retired,
        sibling_during_remove,
        restore_status,
        original_artifacts_match(case.seed),
        case.keep_path.read_bytes() == case.keep_bytes,
    )
