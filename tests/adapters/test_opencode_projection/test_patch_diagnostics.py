from __future__ import annotations

from pathlib import Path

import pytest

from slopgate.adapters.opencode_projection.patch import (
    apply_update,
    parse_patch,
    section_content,
)
from slopgate.engine import evaluate_payload

from .support import enroll_repo, raw_payload, write_source


def test_invalid_patch_identifies_unmatched_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Given: a patch whose context skips a line present in the current file.
    repo = enroll_repo(tmp_path, monkeypatch)
    write_source(repo, "src/app.py", "alpha\nmiddle\nomega\n")
    patch_text = """*** Begin Patch
*** Update File: src/app.py
@@
 alpha
+inserted
 omega
*** End Patch"""

    # When: OpenCode projects the mutation before execution.
    result = evaluate_payload(
        raw_payload(repo, "apply_patch", {"patchText": patch_text}),
        platform="opencode",
    )

    # Then: the block identifies the machine-readable cause and target.
    finding = next(
        item for item in result.findings if item.rule_id == "OC-PROJECTION-001"
    )
    assert finding.metadata.get("projection_status") == "invalid", (
        "an unmatched update must remain fail-closed"
    )
    assert finding.metadata.get("projection_reason") == "update_hunk_mismatch", (
        "the finding must preserve the machine-readable projection cause"
    )
    assert "src/app.py" in str(result.output), (
        "the OpenCode denial must direct the agent to the mismatched target"
    )


def test_apply_update_selects_first_forward_match_for_repeated_anchor() -> None:
    result = apply_update(
        "A = 1\nMARK\nEND\nEND\n",
        (
            "@@",
            " A = 1",
            " MARK",
            "@@",
            " END",
            "+TAIL",
        ),
    )

    assert result == "A = 1\nMARK\nEND\nTAIL\nEND\n", (
        "a repeated anchor must resolve to the first forward match after the previous hunk"
    )


def test_apply_update_rejects_unmatched_hunk() -> None:
    result = apply_update("VALUE = 1\n", ("@@", "-VALUE = 2", "+VALUE = 3"))
    assert result is None, "an unmatched update hunk must remain fail-closed invalid"


def test_apply_update_keeps_forward_cursor_after_line_count_change() -> None:
    result = apply_update(
        "AA\nBB\nCC\n",
        ("@@", "-AA", "-BB", "+XX", "@@", "-CC", "+YY"),
    )

    assert result == "XX\nYY\n", (
        "a line-count-changing hunk must not reject an applicable later hunk"
    )


def test_apply_update_matches_later_hunks_against_original_content() -> None:
    result = apply_update(
        "A\nB\nC\nD\n",
        ("@@", "-B", "@@", " C", "+C2"),
    )

    assert result == "A\nC\nC2\nD\n", (
        "later hunks must locate on the original content, not the mutated buffer"
    )


def test_apply_update_does_not_match_just_inserted_lines() -> None:
    result = apply_update(
        "P\nQ\n",
        ("@@", "-P", "+P", "+Q", "@@", "-Q", "+R"),
    )

    assert result == "P\nQ\nR\n", (
        "a later hunk must not re-match text inserted by an earlier hunk"
    )


def test_apply_update_matches_via_unicode_punctuation_table() -> None:
    result = apply_update("A \u2013 B\n", ("@@", "-A - B", "+A - B"))

    assert result == "A - B\n", (
        "unicode dashes must normalize to ASCII like native opencode"
    )


def test_apply_update_appends_pure_addition_at_end_of_file() -> None:
    result = apply_update("A\nB\n", ("@@", "+C"))

    assert result == "A\nB\nC\n", (
        "a hunk without old lines must append at the end of the file"
    )


def test_apply_update_seeks_anchor_context_before_matching() -> None:
    result = apply_update(
        "END\nA\nEND\n",
        ("@@ A", "-END", "+Z"),
    )

    assert result == "END\nA\nZ\n", (
        "the anchor must advance the cursor before the hunk seeks its target"
    )


def test_apply_update_retries_hunk_with_trailing_blank_line() -> None:
    result = apply_update(
        "A\nB\n",
        ("@@", " A", " ", "+C"),
    )

    assert result == "A\n\nC\nB\n", (
        "a hunk whose old lines end with a blank line must retry without it"
    )


def test_patch_stops_collection_at_end_of_file_marker() -> None:
    patch_text = """*** Begin Patch
*** Update File: src/app.py
@@
 A
+X
*** End of File
-B
+Y
*** End Patch"""

    sections = parse_patch(patch_text)

    assert sections is not None and len(sections) == 1, (
        "the marker must not break patch envelope parsing"
    )
    content = section_content(sections[0], "A\nB\n")
    assert content == "A\nX\nB\n", (
        "the end-of-file marker must terminate chunk collection before the tail lines"
    )
