from __future__ import annotations

from tests.test_ast_rules import (
    BUNDLE_ROOT,
    _assert_denied_by,
    _assert_not_denied,
    evaluate_payload,
    unittest,
)

class TestLongLines(unittest.TestCase):
    def test_long_line_blocked(self) -> None:
        long_line = "x" * 130 + chr(10)
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": "src/main.py", "new_string": long_line},
            "cwd": str(BUNDLE_ROOT),
        }
        result = evaluate_payload(payload)
        _assert_denied_by(result, "PY-CODE-010")
        assert any(finding.rule_id == "PY-CODE-010" for finding in result.findings)

    def test_long_line_blocked_for_top_level_path_edit_shape(self) -> None:
        long_line = "x" * 400 + chr(10)
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {
                "path": "src/main.py",
                "edits": [{"oldText": "x = 1\n", "newText": long_line}],
            },
            "cwd": str(BUNDLE_ROOT),
        }
        result = evaluate_payload(payload)
        _assert_denied_by(result, "PY-CODE-010")
        rule_ids = {finding.rule_id for finding in result.findings}
        assert "PY-CODE-010" in rule_ids, "top-level path edit must hit long-line rule"

    def test_120_ok(self) -> None:
        line = "x" * 120 + chr(10)
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": "src/main.py", "new_string": line},
            "cwd": str(BUNDLE_ROOT),
        }
        result = evaluate_payload(payload)
        _assert_not_denied(result)
        assert all(finding.rule_id != "PY-CODE-010" for finding in result.findings)

    def test_url_exempt(self) -> None:
        line = 'x = "https://example.com/very/long/path/that/exceeds/limit"' + chr(10)
        payload = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": "src/main.py", "new_string": line},
            "cwd": str(BUNDLE_ROOT),
        }
        result = evaluate_payload(payload)
        _assert_not_denied(result)
        assert all(finding.rule_id != "PY-CODE-010" for finding in result.findings)
