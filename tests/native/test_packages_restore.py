"""Native staging snapshots restore committed filesystem state."""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from slopgate.installer.native.packages import (
    native_host_root,
    owned_staging_present,
    restore_staging,
    staging_is_current,
    write_staging,
)
from tests.native.packages_support import (
    HOST_NAME,
    MUTATED_MODE,
    empty_staging_case,
    staging_restore_case,
    tree_bytes,
)


def _restore_bytes_and_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[int, dict[str, bytes], int, bool, int, int, dict[str, bytes]]:
    plan, index, before, snapshot = staging_restore_case(tmp_path, monkeypatch)
    original_mode = stat.S_IMODE(index.stat().st_mode)
    index.write_text("replacement", encoding="utf-8")
    index.chmod(MUTATED_MODE)
    mutated_mode = stat.S_IMODE(index.stat().st_mode)
    status = restore_staging(snapshot)
    return (
        status,
        tree_bytes(plan.entry_root),
        stat.S_IMODE(index.stat().st_mode),
        staging_is_current(plan),
        mutated_mode,
        original_mode,
        before,
    )


def _remove_transaction_created_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[bool, int, bool, bool, bool]:
    plan, snapshot = empty_staging_case(tmp_path, monkeypatch)
    write_staging(plan)
    wrote_stage = plan.entry_root.is_dir()
    status = restore_staging(snapshot)
    return (
        wrote_stage,
        status,
        plan.entry_root.exists(),
        native_host_root(HOST_NAME).exists(),
        owned_staging_present(HOST_NAME),
    )


def test_snapshot_and_restore_staging_restores_bytes_and_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observed = _restore_bytes_and_mode(tmp_path, monkeypatch)
    status, files_after, mode_after, current, mutated_mode, original_mode, before = (
        observed
    )

    assert mutated_mode != original_mode, (
        "the restore regression must change to a read-only mode on every platform"
    )
    assert (status, files_after, mode_after, current) == (
        0,
        before,
        original_mode,
        True,
    ), (
        "staging rollback should restore prior bytes, reported file modes, "
        "ownership metadata, and currentness"
    )


def test_snapshot_restore_removes_new_files_and_empty_directories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wrote_stage, status, entry_exists, host_root_exists, owned = (
        _remove_transaction_created_staging(tmp_path, monkeypatch)
    )

    assert wrote_stage, (
        "the empty snapshot must precede a real staging write before restoration"
    )
    assert (status, entry_exists, host_root_exists, owned) == (
        0,
        False,
        False,
        False,
    ), (
        "rollback of a never-written package should remove only transaction-created empty paths"
    )
