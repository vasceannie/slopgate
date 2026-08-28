from __future__ import annotations

from pathlib import Path

import pytest

from slopgate.adapters.opencode_projection.patch import apply_update
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
