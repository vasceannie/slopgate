"""Smoke tests for the offline L1 eval pack loader."""

from __future__ import annotations

import json
from pathlib import Path

from slopgate.eval import evaluate_case, load_eval_cases, summarize_eval

FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "eval"
    / "l1_holdout_pilot.jsonl"
)


def test_load_pinned_holdout_cases() -> None:
    assert FIXTURE.is_file(), f"missing pinned holdout fixture: {FIXTURE}"
    cases = load_eval_cases(FIXTURE)
    assert len(cases) >= 10
    first = cases[0]
    assert first.get("case_id")
    assert first.get("replay_payload")
    assert isinstance(first.get("expected"), list)


def test_evaluate_case_smoke_on_first_holdout() -> None:
    cases = load_eval_cases(FIXTURE)
    row = evaluate_case(cases[0])
    assert row.get("case_id") == cases[0].get("case_id")
    assert "got_rules" in row
    assert row.get("error") is None


def test_summarize_eval_counts() -> None:
    cases = load_eval_cases(FIXTURE)[:3]
    rows = [evaluate_case(case) for case in cases]
    summary = summarize_eval(rows)
    assert summary["n"] == len(rows)
    assert summary["errors"] == 0
    assert "note" in summary


def test_holdout_meta_matches_jsonl() -> None:
    meta_path = FIXTURE.with_suffix(".meta.json")
    assert meta_path.is_file()
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    cases = load_eval_cases(FIXTURE)
    assert meta["n"] == len(cases)


def test_case_is_replayable_rejects_empty_input() -> None:
    from slopgate.eval import case_is_replayable

    assert case_is_replayable(
        {
            "event_name": "PreToolUse",
            "tool_name": "Bash",
            "replay_payload": {"tool_input": {"command": "ls"}},
        }
    )
    assert not case_is_replayable(
        {
            "event_name": "PostToolUse",
            "tool_name": "Bash",
            "replay_payload": {"tool_input": {"command": "ls"}},
        }
    )
    assert not case_is_replayable(
        {
            "tier": "label_only",
            "event_name": "PreToolUse",
            "tool_name": "Bash",
            "replay_payload": {"tool_input": {"command": "ls"}},
        }
    )


def test_evaluate_pack_skips_label_only_by_default(tmp_path: Path) -> None:
    from slopgate.eval import evaluate_pack

    pack = tmp_path / "pack.jsonl"
    pack.write_text(
        json.dumps(
            {
                "case_id": "replay",
                "tier": "replayable",
                "platform": "claude",
                "event_name": "PreToolUse",
                "tool_name": "Bash",
                "primary_rule": "SHELL-001",
                "expected": [{"rule_id": "SHELL-001"}],
                "replay_payload": {
                    "cwd": "/tmp",
                    "hook_event_name": "PreToolUse",
                    "tool_name": "Bash",
                    "tool_input": {"command": "echo hi"},
                },
            }
        )
        + "\n"
        + json.dumps(
            {
                "case_id": "label",
                "tier": "label_only",
                "platform": "claude",
                "event_name": "PostToolUse",
                "tool_name": "Bash",
                "primary_rule": "SHELL-001",
                "expected": [{"rule_id": "SHELL-001"}],
                "replay_payload": {"tool_input": {}},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    summary = evaluate_pack(pack)
    assert summary["n"] == 1
    assert summary["skipped_label_only"] == 1
    assert summary["replayable_only"] is True
