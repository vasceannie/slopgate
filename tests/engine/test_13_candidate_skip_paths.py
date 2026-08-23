from __future__ import annotations

from pathlib import Path

from pytest import MonkeyPatch

from slopgate._types import ObjectDict
from slopgate.engine import evaluate_payload
from tests.engine.support import write_config_from_defaults, write_slopgate


_MIXED_EDIT_INPUT: list[ObjectDict] = [
    {"file_path": "generated/.pylintrc", "old_string": "", "new_string": "x"},
    {"file_path": "src/.pylintrc", "old_string": "", "new_string": "x"},
]


def test_mixed_multiedit_keeps_unskipped_target_enforced(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    repo = write_slopgate(tmp_path / "repo")
    generated = repo / "generated"
    write_config_from_defaults(
        tmp_path,
        monkeypatch,
        lambda defaults: defaults.update(
            {"skip_paths": [str(generated.resolve() / "*")]}
        ),
    )
    result = evaluate_payload(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "MultiEdit",
            "cwd": str(repo),
            "tool_input": {"edits": _MIXED_EDIT_INPUT},
        }
    )

    linter_findings = [
        finding for finding in result.findings if finding.rule_id == "PY-LINTER-001"
    ]
    assert linter_findings, "the unskipped candidate must remain subject to strict rules"
    assert {
        str(finding.metadata.get("path")) for finding in linter_findings
    } == {"src/.pylintrc"}
