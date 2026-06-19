from __future__ import annotations

import json

from tests.test_engine import Path, assert_not_denied, evaluate_payload, finding_ids

_PI_REPLACE_CONTEXT = (
    "Hook phase: PreToolUse; tool: replace; failure class: quality; "
    "target: tests/example.py.\n\nNext step: remove the suppression and add a "
    "Protocol, TypedDict, overload, or local stub."
)


def test_pi_replace_lines_payload_blocks_type_suppression(bundle_root: Path) -> None:
    payload = {
        "session_id": "t",
        "cwd": str(bundle_root),
        "hook_event_name": "tool_call",
        "tool_name": "replace",
        "tool_input": {
            "path": "tests/example.py",
            "edits": [
                {
                    "start": "before",
                    "end": "after",
                    "lines": [
                        "if callable(callback):",
                        "    callback(payload)  # type: ignore[call-top-callable]",
                    ],
                }
            ],
        },
    }
    result = evaluate_payload(payload, platform="pi")

    assert {
        "rule_present": "PY-TYPE-002" in finding_ids(result),
        "block": result.output.get("block") if result.output else None,
        "context": result.output.get("context") if result.output else None,
    } == {
        "rule_present": True,
        "block": True,
        "context": _PI_REPLACE_CONTEXT,
    }, "Pi replace edits should block suppression comments in edits[].lines"


def test_pi_transcript_style_replace_arguments_blocks_type_suppression(
    bundle_root: Path,
) -> None:
    payload = {
        "session_id": "t",
        "cwd": str(bundle_root),
        "hook_event_name": "tool_call",
        "name": "replace",
        "arguments": {
            "path": "tests/example.py",
            "edits": [
                {
                    "start": "H4X",
                    "end": "H4X",
                    "lines": [
                        "args = _as_mapping(raw_args)  # pyright: ignore[reportUnknownArgumentType]",
                    ],
                }
            ],
        },
    }
    result = evaluate_payload(payload, platform="pi")

    assert {
        "rule_present": "PY-TYPE-002" in finding_ids(result),
        "block": result.output.get("block") if result.output else None,
        "context": result.output.get("context") if result.output else None,
    } == {
        "rule_present": True,
        "block": True,
        "context": _PI_REPLACE_CONTEXT,
    }, "Raw Pi replace arguments should block suppression comments in edits[].lines"


def test_pi_replace_lines_payload_allows_clean_edit(bundle_root: Path) -> None:
    payload = {
        "session_id": "t",
        "cwd": str(bundle_root),
        "hook_event_name": "tool_call",
        "tool_name": "replace",
        "tool_input": {
            "path": "tests/example.py",
            "edits": [
                {
                    "start": "before",
                    "end": "after",
                    "lines": [
                        "if callable(callback):",
                        "    callback(payload)",
                    ],
                }
            ],
        },
    }
    result = evaluate_payload(payload, platform="pi")

    assert "PY-TYPE-002" not in finding_ids(result), (
        "Pi replace edits should allow clean replacement lines"
    )
    assert_not_denied(result)


def test_pi_replace_json_string_edits_block_type_suppression(
    bundle_root: Path,
) -> None:
    payload = {
        "session_id": "t",
        "cwd": str(bundle_root),
        "hook_event_name": "tool_call",
        "tool_name": "replace",
        "tool_input": {
            "path": "tests/example.py",
            "edits": json.dumps(
                [
                    {
                        "oldText": "result = callback(payload)",
                        "newText": "result = callback(payload)  # type: ignore[arg-type]",
                    }
                ]
            ),
        },
    }
    result = evaluate_payload(payload, platform="pi")

    assert {
        "rule_present": "PY-TYPE-002" in finding_ids(result),
        "block": result.output.get("block") if result.output else None,
        "context": result.output.get("context") if result.output else None,
        "has_decoded_suppression": (
            "Suppression(s) found: type ignore for `arg-type`"
            in str(result.output.get("reason") if result.output else "")
        ),
    } == {
        "rule_present": True,
        "block": True,
        "context": _PI_REPLACE_CONTEXT,
        "has_decoded_suppression": True,
    }, "Pi replace should inspect JSON-string encoded edit arrays"


def test_pi_replace_malformed_json_string_edits_do_not_crash(bundle_root: Path) -> None:
    payload = {
        "session_id": "t",
        "cwd": str(bundle_root),
        "hook_event_name": "tool_call",
        "tool_name": "replace",
        "tool_input": {
            "path": "tests/example.py",
            "edits": "[",
        },
    }
    result = evaluate_payload(payload, platform="pi")

    assert "PY-TYPE-002" not in finding_ids(result), (
        "Pi replace should ignore malformed JSON-string edit arrays"
    )
    assert_not_denied(result)
