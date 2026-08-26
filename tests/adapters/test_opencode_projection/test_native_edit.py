from __future__ import annotations

from pathlib import Path

import pytest

from slopgate.engine import evaluate_payload
from .support import (
    enroll_repo,
    plant_stale_symlink_repo,
    projection_for,
    raw_payload,
    write_source,
)


_MALFORMED_HASHLINE_INPUTS = [
    pytest.param(
        {"edits": [{"op": "replace", "pos": "1#KM", "lines": ["VALUE = 2"]}]},
        id="missing-file-path",
    ),
    pytest.param(
        {"filePath": "src/app.py", "edits": "not-a-list"},
        id="non-list-edits",
    ),
    pytest.param(
        {
            "filePath": "src/app.py",
            "edits": [{"op": "delete", "pos": "1#KM", "lines": [""]}],
        },
        id="unsupported-operation",
    ),
    pytest.param(
        {
            "filePath": "src/app.py",
            "edits": [{"op": "replace", "pos": "1#KM", "lines": [2]}],
        },
        id="non-string-line",
    ),
]

_PROTOCOL_SKEW_NATIVE_MUTATIONS = [
    pytest.param(
        "write",
        {"filePath": "src/app.py", "content": "VALUE = 2\n"},
        id="write",
    ),
    pytest.param(
        "Write",
        {"filePath": "src/app.py", "content": "VALUE = 2\n"},
        id="write-alias",
    ),
    pytest.param(
        "edit",
        {"filePath": "src/app.py", "oldString": "VALUE = 1", "newString": "VALUE = 2"},
        id="edit",
    ),
    pytest.param(
        "Edit",
        {"filePath": "src/app.py", "oldString": "VALUE = 1", "newString": "VALUE = 2"},
        id="edit-alias",
    ),
    pytest.param(
        "apply_patch",
        {
            "patchText": (
                "*** Begin Patch\n*** Update File: src/app.py\n@@\n"
                "-VALUE = 1\n+VALUE = 2\n*** End Patch"
            )
        },
        id="apply-patch",
    ),
    pytest.param(
        "ApplyPatch",
        {
            "patchText": (
                "*** Begin Patch\n*** Update File: src/app.py\n@@\n"
                "-VALUE = 1\n+VALUE = 2\n*** End Patch"
            )
        },
        id="apply-patch-alias",
    ),
]


def test_stale_hashline_anchor_defers_validation_to_native_tool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = enroll_repo(tmp_path, monkeypatch)
    write_source(repo, "src/app.py", "VALUE = 1\n")
    tool_input: dict[str, object] = {
        "filePath": "src/app.py",
        "edits": [
            {
                "op": "replace",
                "pos": "1#ZZ",
                "lines": ["VALUE = 2"],
            }
        ],
    }

    result = evaluate_payload(
        raw_payload(repo, "edit", tool_input),
        platform="opencode",
    )
    projection = projection_for(repo, "edit", tool_input)

    assert projection.get("reason") == "stale_hash_anchor"
    assert all(
        finding.rule_id != "OC-PROJECTION-001" for finding in result.findings
    ), "native Edit must own stale hashline validation instead of Slopgate blocking first"


@pytest.mark.parametrize(("tool_name", "tool_input"), _PROTOCOL_SKEW_NATIVE_MUTATIONS)
def test_protocol_skew_defers_to_declared_native_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tool_name: str,
    tool_input: dict[str, object],
) -> None:
    repo = enroll_repo(tmp_path, monkeypatch)
    write_source(repo, "src/app.py", "VALUE = 1\n")
    payload = raw_payload(repo, tool_name, tool_input)
    payload["opencode_tool_contract_version"] = "wrong-contract"

    result = evaluate_payload(payload, platform="opencode")

    assert result.output is None or result.output.get("action") != "block", (
        "declared native mutations must own validation during projection protocol skew"
    )
    assert all(
        finding.rule_id != "OC-PROJECTION-001" for finding in result.findings
    ), "projection protocol skew must not falsely deny a declared native mutation"


@pytest.mark.parametrize("tool_input", _MALFORMED_HASHLINE_INPUTS)
def test_malformed_hashline_edit_remains_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tool_input: dict[str, object],
) -> None:
    repo = enroll_repo(tmp_path, monkeypatch)
    write_source(repo, "src/app.py", "VALUE = 1\n")

    result = evaluate_payload(
        raw_payload(repo, "edit", tool_input),
        platform="opencode",
    )

    assert result.output is not None and result.output.get("action") == "block"
    assert any(
        finding.rule_id == "OC-PROJECTION-001" for finding in result.findings
    ), "malformed native Edit payloads must remain fail-closed"


def test_hashline_edit_against_symlink_snapshot_remains_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, outside = plant_stale_symlink_repo(tmp_path, monkeypatch)
    tool_input: dict[str, object] = {
        "filePath": "src/app.py",
        "edits": [
            {"op": "replace", "pos": "1#KM", "lines": ["VALUE = 2"]}
        ],
    }

    result = evaluate_payload(
        raw_payload(repo, "edit", tool_input),
        platform="opencode",
    )

    assert result.output is not None and result.output.get("action") == "block"
    assert any(
        finding.rule_id == "OC-PROJECTION-001" for finding in result.findings
    ), "stale snapshots must remain fail-closed for hashline edits"
    assert outside.read_text(encoding="utf-8") == "VALUE = 1\n"
