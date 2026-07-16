from __future__ import annotations

from slopgate.engine import evaluate_payload
from tests.test_ast_rules import BUNDLE_ROOT


def test_feature_envy_ignores_capsys_output_inspection() -> None:
    code = (
        "def test_output(capsys):\n"
        "    captured = capsys.readouterr()\n"
        "    assert captured.out.strip()\n"
        "    assert captured.err.strip()\n"
        "    assert captured.out.startswith('ok')\n"
    )
    result = evaluate_payload(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": "tests/test_output.py", "content": code},
            "cwd": str(BUNDLE_ROOT),
        }
    )

    rule_ids = {finding.rule_id for finding in result.findings}
    assert "PY-CODE-012" not in rule_ids, "capsys inspection is not feature envy"


def test_feature_envy_ignores_object_under_test_inspection() -> None:
    code = (
        "def test_result():\n"
        "    result = build_result()\n"
        "    assert result.status == 'ready'\n"
        "    assert result.value == 3\n"
        "    assert result.label == 'done'\n"
    )
    result = evaluate_payload(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": "tests/test_result.py", "content": code},
            "cwd": str(BUNDLE_ROOT),
        }
    )

    rule_ids = {finding.rule_id for finding in result.findings}
    assert "PY-CODE-012" not in rule_ids, "test result inspection is not feature envy"
