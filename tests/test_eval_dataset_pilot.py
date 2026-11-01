"""Smoke tests for the offline L1 eval pack loader."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from slopgate.cli.parsers import build_parser
from slopgate.eval import (
    EvalPackOptions,
    OverlayOutput,
    OverlayProvenance,
    case_is_replayable,
    evaluate_case,
    evaluate_pack,
    load_eval_cases,
    overlay_row_from_eval,
    summarize_eval,
)

FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "eval"
    / "l1_holdout_pilot.jsonl"
)
CI_SLICE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "eval"
    / "l1_ci.jsonl"
)


def test_load_ci_slice_cases() -> None:
    assert CI_SLICE.is_file(), f"missing CI slice fixture: {CI_SLICE}"
    cases = load_eval_cases(CI_SLICE)
    assert len(cases) >= 200
    first = cases[0]
    assert first.get("case_id")
    assert first.get("replay_payload")
    assert first.get("tier") == "replayable"


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


_LABEL_ONLY_OVERRIDES: dict[str, object] = {
    "tier": "label_only",
    "event_name": "PostToolUse",
    "replay_payload": {"tool_input": {}},
}
_SELECTION_COUNT_KEYS = ("n", "skipped_label_only", "replayable_only")


def _bash_case(case_id: str, **overrides: object) -> dict[str, object]:
    """Build a replayable PreToolUse Bash case that no rule flags."""
    case: dict[str, object] = {
        "case_id": case_id,
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
    return {**case, **overrides}


def _write_pack(path: Path, cases: list[dict[str, object]]) -> Path:
    path.write_text("".join(json.dumps(case) + "\n" for case in cases), encoding="utf-8")
    return path


def _mixed_tier_pack(tmp_path: Path) -> Path:
    cases = [_bash_case("replay"), _bash_case("label", **_LABEL_ONLY_OVERRIDES)]
    return _write_pack(tmp_path / "pack.jsonl", cases)


def test_evaluate_pack_skips_label_only_by_default(tmp_path: Path) -> None:
    summary = evaluate_pack(_mixed_tier_pack(tmp_path))

    counts = {key: summary[key] for key in _SELECTION_COUNT_KEYS}
    assert counts == {"n": 1, "skipped_label_only": 1, "replayable_only": True}, (
        "the default run should evaluate only the replayable case"
    )


def test_evaluate_pack_can_include_label_only_cases(tmp_path: Path) -> None:
    options = EvalPackOptions(replayable_only=False)

    summary = evaluate_pack(_mixed_tier_pack(tmp_path), options)

    counts = {key: summary[key] for key in _SELECTION_COUNT_KEYS}
    assert counts == {"n": 2, "skipped_label_only": 0, "replayable_only": False}, (
        "an inclusive run should evaluate every case and skip none"
    )


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _evaluate_with_overlay(
    tmp_path: Path, case: dict[str, object]
) -> tuple[dict[str, object], dict[str, object]]:
    """Evaluate one case with a sidecar; return the summary and its overlay row."""
    pack = _write_pack(tmp_path / "pack.jsonl", [case])
    overlay = tmp_path / "overlay.jsonl"
    summary = evaluate_pack(
        pack, EvalPackOptions(overlay=OverlayOutput(overlay, engine_version="test"))
    )
    return summary, _read_jsonl(overlay)[0]


def test_evaluate_pack_writes_overlay_sidecar(tmp_path: Path) -> None:
    summary, row = _evaluate_with_overlay(tmp_path, _bash_case("overlay-1"))

    assert summary["overlay_rows"] == 1, "summary should count the written rows"
    assert (row["case_id"], row["engine_version"]) == ("overlay-1", "test"), (
        "the sidecar row should identify its case and engine"
    )
    assert (row["current_rules"], row["primary_hit"]) == ([], False), (
        "a clean replay should record no current rules and a primary miss"
    )


def test_overlay_row_rebuilds_from_the_returned_results(tmp_path: Path) -> None:
    case = _bash_case("overlay-1")
    summary, row = _evaluate_with_overlay(tmp_path, case)
    results = summary["results"]
    assert isinstance(results, list), "evaluate_pack must return per-case results"

    rebuilt = overlay_row_from_eval(
        case,
        results[0],
        OverlayProvenance(
            engine_version="test",
            evaluated_at=str(row["evaluated_at"]),
            cwd_kind="as_payload",
        ),
    )

    assert rebuilt == row, "the sidecar should be reproducible from the summary"


def test_evaluate_case_reports_replay_failure_as_data() -> None:
    row = evaluate_case(_bash_case("bad-platform", platform="nonsense"))

    assert row["got_rules"] == [], "a failed replay should report no rules"
    assert str(row["error"]).startswith("ValueError: Unknown platform"), (
        "the failure should be reported on the row rather than abort the pack"
    )


def test_evaluate_pack_keeps_running_past_a_failed_case(tmp_path: Path) -> None:
    pack = _write_pack(
        tmp_path / "pack.jsonl",
        [_bash_case("bad", platform="nonsense"), _bash_case("good")],
    )

    summary = evaluate_pack(pack)

    assert (summary["n"], summary["errors"]) == (2, 1), (
        "one failed replay should be counted without stopping later cases"
    )


@pytest.mark.parametrize(
    "tool_name",
    ("Write", "Edit", "MultiEdit", "NotebookEdit", "apply_patch", "ApplyPatch", "replace", "write"),
)
def test_file_mutation_case_needs_a_target_to_replay(tool_name: str) -> None:
    case = _bash_case(
        "mutation",
        tier=None,
        tool_name=tool_name,
        replay_payload={"tool_input": {"unrelated": "value"}},
    )

    assert not case_is_replayable(case), "a mutation without a target is not replayable"
    assert case_is_replayable({**case, "redacted_paths": ["src/app.py"]}), (
        "a redacted path should supply the mutation's target"
    )


@pytest.mark.parametrize(
    "target_key",
    ("file_path", "filePath", "path", "patch", "patchText", "patch_text", "content"),
)
def test_file_mutation_case_accepts_each_target_key(target_key: str) -> None:
    case = _bash_case(
        "mutation",
        tier=None,
        tool_name="Write",
        replay_payload={"tool_input": {target_key: "value"}},
    )

    assert case_is_replayable(case), f"{target_key} should count as a mutation target"


def _run_cli_eval(tmp_path: Path, overlay: Path) -> int:
    pack = _mixed_tier_pack(tmp_path)
    args = build_parser().parse_args(
        ["eval", "--pack", f"{pack}", "--overlay-out", f"{overlay}", "--include-label-only"]
    )
    return args.func(args)


def test_cli_eval_writes_overlay_through_the_real_parser(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    overlay = tmp_path / "overlay.jsonl"

    exit_code = _run_cli_eval(tmp_path, overlay)

    report = json.loads(capsys.readouterr().out)
    assert exit_code == 0, "a pack with no replay errors should exit cleanly"
    assert (report["n"], report["overlay_rows"]) == (2, 2), (
        "--include-label-only should evaluate and overlay both cases"
    )
    assert [row["case_id"] for row in _read_jsonl(overlay)] == ["replay", "label"], (
        "--overlay-out should write one row per evaluated case"
    )


@pytest.mark.parametrize("flag", ("--force", "--user-only", "--repo-only", "--dry-run"))
def test_migrate_parser_keeps_its_flags(flag: str) -> None:
    args = build_parser().parse_args(["migrate", flag])

    assert getattr(args, flag.removeprefix("--").replace("-", "_")), (
        f"{flag} should remain a store-true migrate flag"
    )
