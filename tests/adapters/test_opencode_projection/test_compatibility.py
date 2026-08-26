from __future__ import annotations

from pathlib import Path

import pytest

from slopgate.engine import evaluate_payload
from .support import enroll_repo, write_source


def test_compatibility_pre_tool_use_does_not_require_native_projection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = enroll_repo(tmp_path, monkeypatch)
    source = write_source(repo, "src/app.py", "VALUE = 1\n")

    result = evaluate_payload(
        {
            "hook_event_name": "PreToolUse",
            "hook_source": "opencode-plugin",
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(source),
                "edits": [{"old_text": "VALUE = 1", "new_text": "VALUE = 2"}],
            },
            "cwd": str(repo),
        },
        platform="opencode",
    )

    assert all(finding.rule_id != "OC-PROJECTION-001" for finding in result.findings), (
        "Claude-compatibility replay must defer mutation projection to native tool.execute.before"
    )
