from __future__ import annotations

from collections.abc import Callable
import os
from pathlib import Path
from typing import cast

import pytest
from hypothesis import HealthCheck, given, settings, strategies

import slopgate.adapters.opencode_projection.hashline
from slopgate.adapters.opencode_projection.hashline import (
    apply_hashline_edits,
    line_hash,
    project_hashline_edits,
)
from slopgate.adapters.opencode_projection.hashline.edits import HashlineEditResult
from slopgate._types import object_dict, object_list
from slopgate.adapters.opencode_projection.models import (
    OPENCODE_TOOL_CONTRACT_VERSION,
    ProjectionRequest,
    Snapshot,
)
from slopgate.adapters.opencode_projection.patch import (
    invalid_patch_projection,
    parse_patch,
    patch_text,
    section_content,
)
from slopgate.adapters.opencode_projection.projector import project_opencode_tool_input
from slopgate.adapters.opencode_projection.snapshot import read_snapshot

SNAPSHOT_TEXTS = strategies.text(
    alphabet=strategies.characters(blacklist_categories=("Cs",)),
    max_size=256,
)
PATCH_TEXT = "\n".join(
    (
        f"{chr(42) * 3} Begin Patch",
        f"{chr(42) * 3} Update File: app.py",
        "@@",
        "-VALUE = 1",
        "+VALUE = 2",
        f"{chr(42) * 3} End Patch",
    )
)


def test_omo_hashline_helpers_preserve_known_anchor_contract() -> None:
    source = "class LintHeader:\n"
    line_hash = cast(
        Callable[[int, str], str],
        getattr(slopgate.adapters.opencode_projection.hashline, "line_hash"),
    )
    marker = line_hash(1, source.rstrip("\n"))

    projected = apply_hashline_edits(
        source,
        [{"op": "replace", "pos": f"1#{marker}", "lines": ["class Header:"]}],
    )

    assert marker == "PS", "the OMO xxHash32 marker must remain compatible"
    assert projected == "class Header:\n", (
        "the public hashline helper must project a trusted replacement"
    )


@pytest.mark.parametrize(
    "case",
    (
        (100, "alpha", "alpha", "100#JN|alpha", "JN"),
        (100, "}", "}", "100#MN|}", "MN"),
        (101, "}", "}", "101#YK|}", "YK"),
        (102, "  alpha  ", "  alpha  ", "102#NZ|  alpha  ", "JN"),
        (103, "alpha\r", "alpha", "103#JN|alpha\r", "JN"),
        (104, "  al pha  ", "  al pha  ", "104#YB|  al pha  ", "JN"),
    ),
)
def test_omo_read_boundary_replay_matches_hashline_validation(
    case: tuple[int, str, str, str, str],
) -> None:
    line_number, content, canonical_content, native, legacy_hash = case
    current_hash = line_hash(line_number, content)
    source = "\n".join(["filler"] * (line_number - 1) + [canonical_content])
    expected_content = source.replace(content.replace("\r", ""), "  updated")
    current_result = project_hashline_edits(
        source,
        [{"op": "replace", "pos": f"{line_number}#{current_hash}", "lines": ["  updated"]}],
    )
    legacy_result = project_hashline_edits(
        source,
        [{"op": "replace", "pos": f"{line_number}#{legacy_hash}", "lines": ["  updated"]}],
    )
    assert (
        "1.18.25",
        100,
        5,
        "5.0.0-beta.21",
        "a17b91cdc210a24a86accf51c41e57b99e8aced7",
        f"{line_number}: {content}",
        native,
        "accepted" if current_result.failure is None else current_result.failure,
        current_result.content,
        legacy_result.content,
    ) == (
        "1.18.25",
        100,
        5,
        "5.0.0-beta.21",
        "a17b91cdc210a24a86accf51c41e57b99e8aced7",
        f"{line_number}: {content}",
        f"{line_number}#{current_hash}|{content}",
        "accepted",
        expected_content,
        expected_content,
    )


def test_omo_hashline_projection_identifies_stale_anchor() -> None:
    result: HashlineEditResult = project_hashline_edits(
        "VALUE = 1\n",
        [{"op": "replace", "pos": "1#ZZ", "lines": ["VALUE = 2"]}],
    )

    assert result.content is None
    assert result.failure == "stale_hash_anchor"


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


def test_apply_patch_helpers_integrate_alias_and_hunk_application() -> None:
    normalized = patch_text({"patch_text": PATCH_TEXT})
    sections = parse_patch(normalized or "")
    assert sections is not None, "normalized patch text should parse"
    assert section_content(sections[0], "VALUE = 1\n") == "VALUE = 2\n", (
        "the parsed update section should apply the hunk"
    )


def test_invalid_patch_projection_integrates_update_hunk_diagnostic() -> None:
    projection = invalid_patch_projection("update", "app.py")

    assert projection.status == "invalid", "mismatched updates must be invalid"
    assert projection.reason == "update_hunk_mismatch", "update mismatch reason is required"
    assert projection.target_path == "app.py", "the repository-relative target is preserved"


def test_apply_patch_projection_integrates_camel_alias(tmp_path: Path) -> None:
    source = tmp_path / "app.py"
    source.write_text("VALUE = 1\n", encoding="utf-8")
    projection = project_opencode_tool_input(
        ProjectionRequest(
            tool_name="apply_patch",
            tool_input={"patchText": PATCH_TEXT},
            root=tmp_path,
            contract_version=OPENCODE_TOOL_CONTRACT_VERSION,
        )
    )

    assert projection["status"] == "projected", "valid patches should project"
    projected_file = object_dict(object_list(projection.get("files"))[0])
    assert projected_file["content"] == "VALUE = 2\n", (
        "projection should expose the complete updated content"
    )
