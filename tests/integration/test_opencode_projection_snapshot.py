from __future__ import annotations

import os
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings, strategies

from slopgate.adapters.opencode_projection.models import Snapshot
from slopgate.adapters.opencode_projection.snapshot import read_snapshot

SNAPSHOT_TEXTS = strategies.text(
    alphabet=strategies.characters(blacklist_categories=("Cs",)),
    max_size=256,
)


def test_projection_snapshot_rejects_file_identity_change(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "app.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    before = source.stat()
    after = os.stat_result(
        (
            before.st_mode,
            before.st_ino,
            before.st_dev,
            before.st_nlink,
            before.st_uid,
            before.st_gid,
            before.st_size,
            before.st_atime,
            before.st_mtime + 1,
            before.st_ctime,
        )
    )
    calls = 0
    original_fstat = os.fstat

    def unstable_fstat(descriptor: int) -> os.stat_result:
        nonlocal calls
        calls += 1
        if calls == 1:
            return before
        if calls == 2:
            return after
        return original_fstat(descriptor)

    monkeypatch.setattr(os, "fstat", unstable_fstat)

    assert read_snapshot(tmp_path, "app.py") == "stale", (
        "the projection seam must reject content read across a file identity change"
    )


def test_projection_snapshot_rejects_symlink_target(tmp_path: Path) -> None:
    source = tmp_path / "app.py"
    alias = tmp_path / "alias.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    alias.symlink_to(source)

    assert read_snapshot(tmp_path, "alias.py") == "stale", (
        "descriptor-relative snapshots must not follow symlink targets"
    )


@given(SNAPSHOT_TEXTS)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_projection_snapshot_round_trips_stable_text(
    tmp_path: Path,
    content: str,
) -> None:
    (tmp_path / "app.py").write_text(content, encoding="utf-8")
    snapshot = read_snapshot(tmp_path, "app.py")

    assert isinstance(snapshot, Snapshot), "stable UTF-8 files should produce snapshots"
    assert snapshot.content == content, (
        "descriptor reads must preserve arbitrary UTF-8 text without newline translation"
    )
