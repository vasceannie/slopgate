"""Build and inspect a staged package rollback integration scenario."""

from __future__ import annotations

import stat
from dataclasses import dataclass
from pathlib import Path

import pytest

from slopgate.installer.native.artifacts import ArtifactSnapshot, capture_artifact
from slopgate.installer.native.packages import (
    PackagePlan,
    StagingSnapshot,
    package_plan,
    snapshot_staging,
    staging_is_current,
    write_staging,
)
from tests.native.environment import isolate_native_data_dirs
from tests.native.packages_support import HOST_NAME, renderer

ORIGINAL_MODE = 0o640
MUTATED_MODE = stat.S_IREAD
INITIAL_BYTES = b"initial staged payload\n"
RECREATED_GHOST_BYTES = b"created after staging rollback\n"


@dataclass(frozen=True, slots=True)
class RestoreCase:
    plan: PackagePlan
    snapshot: StagingSnapshot
    artifact: Path
    artifact_snapshot: ArtifactSnapshot
    ghost: Path
    ghost_snapshot: ArtifactSnapshot
    expected_files: dict[str, bytes]
    expected_mode: int


def prepare_restore_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> RestoreCase:
    """Write and snapshot a plan, then mutate one owned file and add one new file."""
    isolate_native_data_dirs(monkeypatch, tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    plan = package_plan(HOST_NAME, render=renderer)
    write_staging(plan)
    artifact = plan.entry_root / "index.ts"
    artifact.chmod(ORIGINAL_MODE)
    expected_mode = stat.S_IMODE(artifact.stat().st_mode)
    artifact_snapshot = capture_artifact(artifact)
    snapshot = snapshot_staging(plan)
    expected_files = {
        str(path.relative_to(plan.entry_root)): path.read_bytes()
        for path in sorted(plan.entry_root.rglob("*"))
        if path.is_file()
    }
    artifact.write_bytes(INITIAL_BYTES)
    artifact.chmod(MUTATED_MODE)
    ghost = plan.entry_root / "new-transaction-file.txt"
    ghost_snapshot = capture_artifact(ghost)
    ghost.write_bytes(b"created during transaction\n")
    return RestoreCase(
        plan,
        snapshot,
        artifact,
        artifact_snapshot,
        ghost,
        ghost_snapshot,
        expected_files,
        expected_mode,
    )


def mutate_artifact_again(case: RestoreCase) -> None:
    """Make a second committed mutation after staging rollback completes."""
    case.artifact.write_bytes(b"second artifact mutation\n")
    case.artifact.chmod(MUTATED_MODE)
    case.ghost.write_bytes(RECREATED_GHOST_BYTES)


def observe_restore_case(case: RestoreCase, staging_status: int) -> tuple[object, ...]:
    """Collect bytes, supported mode, absence and staging-currentness after restore."""
    files_after = {
        str(path.relative_to(case.plan.entry_root)): path.read_bytes()
        for path in sorted(case.plan.entry_root.rglob("*"))
        if path.is_file()
    }
    return (
        staging_status,
        files_after,
        stat.S_IMODE(case.artifact.stat().st_mode),
        case.ghost.exists(),
        staging_is_current(case.plan),
    )
