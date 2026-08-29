from __future__ import annotations

from pathlib import Path

import pytest

from slopgate._types import ObjectDict, object_dict, object_list
from slopgate.adapters.opencode_projection.hashline import line_hash
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


def _range_replacement_input() -> ObjectDict:
    return {
        "filePath": "src/app.py",
        "edits": [
            {
                "op": "replace",
                "pos": "1#XB",
                "end": "4#ZT",
                "lines": [
                    "from sample import (",
                    "    added,",
                    "    first,",
                    "    second,",
                    ")",
                ],
            }
        ],
    }


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
    assert all(finding.rule_id != "OC-PROJECTION-001" for finding in result.findings), (
        "native Edit must own stale hashline validation instead of Slopgate blocking first"
    )


def test_hashline_range_replacement_preserves_unchanged_boundary_lines(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = enroll_repo(tmp_path, monkeypatch)
    source = "from sample import (\n    first,\n    second,\n)\n"
    write_source(repo, "src/app.py", source)
    tool_input = _range_replacement_input()

    projection = projection_for(repo, "edit", tool_input)
    projected = object_dict(object_list(projection.get("files"))[0])

    assert projected["content"] == (
        "from sample import (\n    added,\n    first,\n    second,\n)\n"
    ), "full-range replacement must retain unchanged syntax boundaries"


def test_hashline_range_replacement_avoids_false_ast_denial(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = enroll_repo(tmp_path, monkeypatch)
    write_source(
        repo, "src/app.py", "from sample import (\n    first,\n    second,\n)\n"
    )
    tool_input = _range_replacement_input()

    result = evaluate_payload(
        raw_payload(repo, "edit", tool_input), platform="opencode"
    )

    ast_findings = [
        finding for finding in result.findings if finding.rule_id == "PY-AST-001"
    ]
    assert ast_findings == [], (
        "valid projected Python must not be falsely denied as a parse error"
    )


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
    assert all(finding.rule_id != "OC-PROJECTION-001" for finding in result.findings), (
        "projection protocol skew must not falsely deny a declared native mutation"
    )


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
    assert any(finding.rule_id == "OC-PROJECTION-001" for finding in result.findings), (
        "malformed native Edit payloads must remain fail-closed"
    )


def test_hashline_edit_against_symlink_snapshot_remains_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, outside = plant_stale_symlink_repo(tmp_path, monkeypatch)
    tool_input: dict[str, object] = {
        "filePath": "src/app.py",
        "edits": [{"op": "replace", "pos": "1#KM", "lines": ["VALUE = 2"]}],
    }

    result = evaluate_payload(
        raw_payload(repo, "edit", tool_input),
        platform="opencode",
    )

    assert result.output is not None and result.output.get("action") == "block"
    assert any(finding.rule_id == "OC-PROJECTION-001" for finding in result.findings), (
        "stale snapshots must remain fail-closed for hashline edits"
    )
    assert outside.read_text(encoding="utf-8") == "VALUE = 1\n"


_LIVE_CONTRACT_SOURCE = (
    "".join(f"LINE_{number} = {number}\n" for number in range(1, 25))
    + 'AUTH_RESULT_AUTHENTICATED: Final[AuthResult] = "authenticated"\n'
)
_LINE_25_ANCHOR = "25#" + line_hash(25, _LIVE_CONTRACT_SOURCE.splitlines()[24])
_MFA_LINE = 'AUTH_RESULT_MFA_REQUIRED: Final[AuthResult] = "mfa_required"\n'
_LIVE_PROJECTED_CONTENT = _LIVE_CONTRACT_SOURCE.replace(
    'AUTH_RESULT_AUTHENTICATED: Final[AuthResult] = "authenticated"\n',
    'AUTH_RESULT_AUTHENTICATED: Final[AuthResult] = "authenticated"\n' + _MFA_LINE,
)
_LIVE_EDIT_LINES = [
    'AUTH_RESULT_AUTHENTICATED: Final[AuthResult] = "authenticated"',
    _MFA_LINE.rstrip("\n"),
]


def _first_projected_file(projection: ObjectDict) -> ObjectDict:
    return object_dict(object_list(projection.get("files"))[0])


def test_hashline_live_op_form_edit_projects_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = enroll_repo(tmp_path, monkeypatch)
    write_source(repo, "src/app.py", _LIVE_CONTRACT_SOURCE)
    tool_input = {
        "filePath": "src/app.py",
        "edits": [{"op": "replace", "pos": _LINE_25_ANCHOR, "lines": _LIVE_EDIT_LINES}],
    }

    projected = projection_for(repo, "edit", tool_input)
    projected_file = _first_projected_file(projected)

    assert projected["status"] == "projected", (
        "an op-form edit with an in-alphabet anchor must project an edit"
    )
    assert projected_file.get("operation") == "edit", (
        "a hashline replacement against an existing file must project as an edit"
    )
    assert projected_file.get("content") == _LIVE_PROJECTED_CONTENT, (
        "the projected edit must insert MFA_REQUIRED after the anchor line"
    )


_INVALID_ANCHOR_INPUT: dict[str, object] = {
    "filePath": "src/app.py",
    "edits": [{"op": "replace", "pos": "25#SL", "lines": ["X"]}],
}
_BOOLEAN_APPEND_INPUT: dict[str, object] = {
    "filePath": "src/app.py",
    "edits": [{"append": True, "pos": _LINE_25_ANCHOR, "lines": ["X"]}],
}


def test_hashline_live_invalid_anchor_remains_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = enroll_repo(tmp_path, monkeypatch)
    write_source(repo, "src/app.py", _LIVE_CONTRACT_SOURCE)

    result = evaluate_payload(
        raw_payload(repo, "edit", _INVALID_ANCHOR_INPUT), platform="opencode"
    )

    assert result.output is not None, "the live anchor payload must be evaluated"
    assert result.output.get("action") == "block", (
        "an anchor outside the nibble alphabet must remain fail-closed"
    )
    assert any(finding.rule_id == "OC-PROJECTION-001" for finding in result.findings), (
        "an anchor outside the nibble alphabet must deny with OC-PROJECTION-001"
    )


def test_hashline_live_boolean_append_remains_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = enroll_repo(tmp_path, monkeypatch)
    write_source(repo, "src/app.py", _LIVE_CONTRACT_SOURCE)

    result = evaluate_payload(
        raw_payload(repo, "edit", _BOOLEAN_APPEND_INPUT), platform="opencode"
    )

    assert result.output is not None, (
        "the live boolean-append payload must be evaluated"
    )
    assert result.output.get("action") == "block", (
        "a boolean append alias outside the OMO contract must remain fail-closed"
    )
    assert any(finding.rule_id == "OC-PROJECTION-001" for finding in result.findings), (
        "a boolean append alias must deny with OC-PROJECTION-001"
    )
