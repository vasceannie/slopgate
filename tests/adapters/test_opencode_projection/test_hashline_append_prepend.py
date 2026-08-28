from __future__ import annotations

from pathlib import Path

import pytest

from slopgate._types import object_dict, object_list
from slopgate.adapters.opencode_projection.hashline import line_hash
from slopgate.engine import evaluate_payload
from .support import enroll_repo, projection_for, raw_payload, write_source


@pytest.mark.parametrize(
    ("operation", "expected"),
    [
        pytest.param("append", "VALUE = 1", id="append-at-eof"),
        pytest.param("prepend", "VALUE = 1", id="prepend-at-bof"),
    ],
)
def test_omo_hashline_unanchored_insertions_create_missing_file(
    tmp_path: Path,
    operation: str,
    expected: str,
) -> None:
    projection = projection_for(
        tmp_path,
        "edit",
        {
            "filePath": "src/new.py",
            "edits": [{"op": operation, "lines": ["VALUE = 1"]}],
        },
    )
    projected = object_dict(object_list(projection.get("files"))[0])

    assert projection["status"] == "projected", (
        "native unanchored insertion should create a missing file"
    )
    assert projected == {
        "path": "src/new.py",
        "content": expected,
        "operation": "add",
        "preimage_sha256": None,
    }, "missing-file creation must expose the native add effect"


@pytest.mark.parametrize(
    ("edit", "expected_reason"),
    [
        pytest.param({"op": "append"}, None, id="omitted-lines"),
        pytest.param({"op": "append", "lines": None}, "empty_insertion", id="null-lines"),
        pytest.param({"op": "prepend", "lines": []}, "empty_insertion", id="empty-lines"),
    ],
)
def test_omo_hashline_zero_line_insertions_remain_invalid(
    tmp_path: Path,
    edit: dict[str, object], expected_reason: str | None,
) -> None:
    write_source(tmp_path, "src/app.py", "VALUE = 1")

    projection = projection_for(
        tmp_path,
        "edit",
        {"filePath": "src/app.py", "edits": [edit]},
    )

    assert projection["status"] == "invalid", "zero-line insertions must remain invalid"
    assert projection.get("reason") == expected_reason, (
        "invalid insertion payloads must retain their available diagnostic reason"
    )


def test_omo_hashline_prepend_single_line_echo_is_preserved(
    tmp_path: Path,
) -> None:
    write_source(tmp_path, "src/app.py", "class LintHeader:\n")

    projection = projection_for(
        tmp_path,
        "edit",
        {
            "filePath": "src/app.py",
            "edits": [
                {
                    "op": "prepend",
                    "pos": "1#PS",
                    "lines": ["class LintHeader:"],
                }
            ],
        },
    )
    projected = object_dict(object_list(projection.get("files"))[0])

    assert projected["content"] == "class LintHeader:\nclass LintHeader:\n", (
        "native prepend keeps a single-line anchor echo"
    )


def test_omo_hashline_blank_anchor_is_unanchored(tmp_path: Path) -> None:
    write_source(tmp_path, "src/app.py", "VALUE = 1")

    projection = projection_for(
        tmp_path,
        "edit",
        {
            "filePath": "src/app.py",
            "edits": [{"op": "append", "pos": " ", "lines": ["VALUE = 2"]}],
        },
    )
    projected = object_dict(object_list(projection.get("files"))[0])

    assert projected["content"] == "VALUE = 1\nVALUE = 2", (
        "blank anchors must use unanchored EOF insertion semantics"
    )


def test_omo_hashline_insertions_preserve_separators_and_no_final_newline(
    tmp_path: Path,
) -> None:
    write_source(tmp_path, "src/app.py", "VALUE = 1")

    projection = projection_for(
        tmp_path,
        "edit",
        {
            "filePath": "src/app.py",
            "edits": [{"op": "append", "lines": ["A", "", "B"]}],
        },
    )
    projected = object_dict(object_list(projection.get("files"))[0])

    assert projected["content"] == "VALUE = 1\nA\n\nB", (
        "native insertion must not infer or add declaration separators"
    )


def test_omo_hashline_insertions_preserve_bom_and_crlf(
    tmp_path: Path,
) -> None:
    source = "\ufeffVALUE = 1\r\nVALUE = 2\r\n"
    write_source(tmp_path, "src/app.py", source)
    anchor = f"1#{line_hash(1, 'VALUE = 1')}"

    projection = projection_for(
        tmp_path,
        "edit",
        {
            "filePath": "src/app.py",
            "edits": [{"op": "append", "pos": anchor, "lines": ["VALUE = 3"]}],
        },
    )
    projected = object_dict(object_list(projection.get("files"))[0])

    assert projected["content"] == "\ufeffVALUE = 1\r\nVALUE = 3\r\nVALUE = 2\r\n", (
        "native insertion must restore the source BOM and line ending"
    )


@pytest.mark.parametrize("operation", [pytest.param("append"), pytest.param("prepend")])
def test_missing_file_hashline_insertions_are_available_to_native_tool(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    repo = enroll_repo(tmp_path, monkeypatch)
    tool_input: dict[str, object] = {
        "filePath": "src/new.py",
        "edits": [{"op": operation, "lines": ["VALUE = 1"]}],
    }

    result = evaluate_payload(
        raw_payload(repo, "edit", tool_input),
        platform="opencode",
    )

    assert result.output is None or result.output.get("action") != "block", (
        "native missing-file append/prepend creation must not be falsely denied"
    )
    assert all(finding.rule_id != "OC-PROJECTION-001" for finding in result.findings), (
        "projected native creation must bypass unresolved-projection denial"
    )


def test_omo_hashline_single_line_append_echo_is_rejected(tmp_path: Path) -> None:
    write_source(tmp_path, "src/app.py", "class LintHeader:\n")
    anchor = f"1#{line_hash(1, 'class LintHeader:')}"

    projection = projection_for(
        tmp_path,
        "edit",
        {
            "filePath": "src/app.py",
            "edits": [
                {"op": "append", "pos": anchor, "lines": ["class LintHeader:"]}
            ],
        },
    )

    assert projection["status"] == "invalid", "append echo must remain invalid"
    assert projection.get("reason") == "empty_insertion", (
        "echo-stripped insertions must retain a diagnostic reason"
    )
