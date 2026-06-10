from __future__ import annotations

import json
from pathlib import Path

import pytest

from slopgate._types import ObjectDict, object_dict
from slopgate.engine import evaluate_payload
from tests.support import BUNDLE_ROOT, assert_denied_by, assert_not_denied, finding_ids


class TestBaselineGuard:
    def _write_baseline(self, tmp_path: Path, rules: dict[str, list[str]]) -> Path:
        _ = (tmp_path / "slopgate.toml").write_text(
            "[slopgate]\nenabled = true\n", encoding="utf-8"
        )
        p = tmp_path / "baselines.json"
        _ = p.write_text(
            json.dumps(
                {"generated_at": "2026-01-01", "rules": rules, "schema_version": 1}
            )
        )
        return p

    def test_increase_blocked(self, tmp_path: Path) -> None:
        existing = self._write_baseline(tmp_path, {"high-complexity": ["h1", "h2"]})
        new_content = json.dumps(
            {
                "generated_at": "2026-01-02",
                "rules": {"high-complexity": ["h1", "h2", "h3", "h4"]},
                "schema_version": 1,
            }
        )
        payload: ObjectDict = object_dict(
            {
                "session_id": "t",
                "cwd": str(tmp_path),
                "hook_event_name": "PreToolUse",
                "tool_name": "Write",
                "tool_input": {"file_path": str(existing), "content": new_content},
            }
        )
        result = evaluate_payload(payload)
        assert_denied_by(result, "BASELINE-001", "increasing the baseline")
        assert "BASELINE-001" in finding_ids(result), (
            "baseline count increases should remain blocked"
        )

    def test_relative_baseline_path_uses_payload_cwd(self, tmp_path: Path) -> None:
        self._write_baseline(tmp_path, {"high-complexity": ["h1", "h2"]})
        new_content = json.dumps(
            {
                "generated_at": "2026-01-02",
                "rules": {"high-complexity": ["h1", "h2", "h3"]},
                "schema_version": 1,
            }
        )
        payload: ObjectDict = object_dict(
            {
                "session_id": "t",
                "cwd": str(tmp_path),
                "hook_event_name": "PreToolUse",
                "tool_name": "Write",
                "tool_input": {"file_path": "baselines.json", "content": new_content},
            }
        )

        result = evaluate_payload(payload)

        assert_denied_by(result, "BASELINE-001", "increasing the baseline")
        assert "BASELINE-001" in finding_ids(result)

    def test_new_nonempty_baseline_creation_blocked(self, tmp_path: Path) -> None:
        _ = (tmp_path / "slopgate.toml").write_text(
            "[slopgate]\nenabled = true\n", encoding="utf-8"
        )
        new_content = json.dumps(
            {
                "generated_at": "2026-01-02",
                "rules": {"high-complexity": ["h1"]},
                "schema_version": 1,
            }
        )
        payload: ObjectDict = object_dict(
            {
                "session_id": "t",
                "cwd": str(tmp_path),
                "hook_event_name": "PreToolUse",
                "tool_name": "Write",
                "tool_input": {"file_path": "baselines.json", "content": new_content},
            }
        )

        result = evaluate_payload(payload)

        assert_denied_by(result, "BASELINE-001", "Creating a populated baseline")
        assert "BASELINE-001" in finding_ids(result)

    @pytest.mark.parametrize(
        "command",
        [
            "quality-gate baseline .",
            "slopgate lint baseline .",
            "slopgate   lint baseline .",
            "slopgate lint    baseline .",
            "QUALITY_GENERATE_BASELINE=1 slopgate lint baseline .",
            "env QUALITY_GENERATE_BASELINE=1 /home/trav/.local/bin/slopgate lint baseline .",
            "python -m slopgate lint baseline .",
            "python3 -m slopgate lint baseline .",
            "vfc lint baseline .",
        ],
    )
    def test_repo_wide_baseline_commands_blocked(self, command: str) -> None:
        payload: ObjectDict = object_dict(
            {
                "session_id": "t",
                "cwd": str(BUNDLE_ROOT),
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": command},
            }
        )
        result = evaluate_payload(payload)
        assert_denied_by(result, "BASELINE-001", "technical debt")
        assert "BASELINE-001" in finding_ids(result), (
            "repo-wide baseline commands should remain blocked"
        )

    def test_decrease_allowed(self, tmp_path: Path) -> None:
        existing = self._write_baseline(
            tmp_path, {"high-complexity": ["h1", "h2", "h3"]}
        )
        new_content = json.dumps(
            {
                "generated_at": "2026-01-02",
                "rules": {"high-complexity": ["h1"]},
                "schema_version": 1,
            }
        )
        payload: ObjectDict = object_dict(
            {
                "session_id": "t",
                "cwd": str(tmp_path),
                "hook_event_name": "PreToolUse",
                "tool_name": "Write",
                "tool_input": {"file_path": str(existing), "content": new_content},
            }
        )
        result = evaluate_payload(payload)
        assert_not_denied(result)
        assert "BASELINE-001" not in finding_ids(result), (
            "baseline count decreases should remain allowed"
        )
