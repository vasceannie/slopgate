"""Property tests for the offline eval pack loader, selection, and overlay rows."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from hypothesis import given, settings, strategies

from slopgate.eval import (
    EvalPackOptions,
    OverlayProvenance,
    case_is_replayable,
    evaluate_case,
    evaluate_pack,
    load_eval_cases,
    overlay_row_from_eval,
)

ENGINE_MAX_EXAMPLES = 15
MAX_PACK_CASES = 6

_JSON_SCALARS = strategies.one_of(
    strategies.none(), strategies.booleans(), strategies.integers(), strategies.text()
)
_NON_EMPTY_CASES = strategies.dictionaries(
    strategies.text(min_size=1), _JSON_SCALARS, min_size=1, max_size=4
)
_RULE_IDS = strategies.sampled_from(("SHELL-001", "GIT-001", "PY-CODE-008", "STOP-001"))
_PACK_TIERS = strategies.lists(
    strategies.sampled_from(("replayable", "label_only")), max_size=MAX_PACK_CASES
)
_PACK_LIMITS = strategies.one_of(
    strategies.none(), strategies.integers(min_value=0, max_value=MAX_PACK_CASES)
)


def _bash_case(case_id: str, **overrides: object) -> dict[str, object]:
    return {
        "case_id": case_id,
        "tier": "replayable",
        "platform": "claude",
        "event_name": "PreToolUse",
        "tool_name": "Bash",
        "replay_payload": {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "echo hi"},
        },
        **overrides,
    }


def _load_jsonl_lines(lines: list[str]) -> list[dict[str, object]]:
    # Hypothesis reruns the body per example, so pytest's per-test tmp_path won't do.
    with tempfile.TemporaryDirectory() as tmp:
        pack = Path(tmp) / "pack.jsonl"
        pack.write_text("\n".join(lines), encoding="utf-8")
        return load_eval_cases(pack)


def _summarize_tiers(tiers: list[str], options: EvalPackOptions) -> dict[str, object]:
    cases = [_bash_case(f"case-{i}", tier=tier) for i, tier in enumerate(tiers)]
    with tempfile.TemporaryDirectory() as tmp:
        pack = Path(tmp) / "pack.jsonl"
        pack.write_text("".join(json.dumps(case) + "\n" for case in cases), encoding="utf-8")
        return evaluate_pack(pack, options)


@given(cases=strategies.lists(_NON_EMPTY_CASES, max_size=5))
def test_load_eval_cases_round_trips_rows_and_ignores_blank_lines(
    cases: list[dict[str, object]],
) -> None:
    lines = [line for case in cases for line in (json.dumps(case), "   ")]

    assert _load_jsonl_lines(lines) == cases, "every non-empty row should load in order"


@given(
    tier=strategies.sampled_from(("replayable", "label_only")),
    event=strategies.text(),
    tool_input=strategies.dictionaries(strategies.text(), _JSON_SCALARS, max_size=2),
)
def test_case_is_replayable_trusts_a_declared_tier_over_the_payload(
    tier: str, event: str, tool_input: dict[str, object]
) -> None:
    case: dict[str, object] = {
        "tier": tier,
        "event_name": event,
        "replay_payload": {"tool_input": tool_input},
    }

    assert case_is_replayable(case) is (tier == "replayable"), (
        "a declared tier should decide replayability on its own"
    )


@given(
    event=strategies.text(min_size=1).filter(
        lambda value: value not in {"PreToolUse", "tool.execute.before"}
    )
)
def test_case_is_replayable_rejects_events_outside_pretool(event: str) -> None:
    case = _bash_case("event", tier=None, event_name=event)

    assert not case_is_replayable(case), "only pre-tool events can be replayed"


@given(
    rules=strategies.lists(_RULE_IDS, max_size=4),
    primary_hit=strategies.booleans(),
    case_id=strategies.text(),
)
def test_overlay_row_from_eval_reports_current_rules_without_mutating_inputs(
    rules: list[str], primary_hit: bool, case_id: str
) -> None:
    case: dict[str, object] = {"case_id": case_id, "expected": ["historical"]}
    result: dict[str, object] = {"got_rules": list(rules), "primary_hit": primary_hit}
    case_before, result_before = dict(case), dict(result)
    provenance = OverlayProvenance(engine_version="test", evaluated_at="now")

    row = overlay_row_from_eval(case, result, provenance)

    summary = (row["case_id"], row["current_rules"], row["primary_hit"])
    assert summary == (case_id, rules, primary_hit), "the row should copy this verdict"
    assert row["primary_rule_current"] == (rules[0] if rules else "_CLEAN"), (
        "the current primary should be the first rule, or the clean marker"
    )
    assert (case, result) == (case_before, result_before), (
        "the overlay must never rewrite historical labels"
    )


@settings(max_examples=ENGINE_MAX_EXAMPLES, deadline=None)
@given(expected=strategies.lists(_RULE_IDS, max_size=6))
def test_evaluate_case_dedupes_expected_rules_in_first_seen_order(
    expected: list[str],
) -> None:
    case = _bash_case("dedupe", expected=[{"rule_id": rule} for rule in expected])

    row = evaluate_case(case)

    assert row["expected_rules"] == list(dict.fromkeys(expected)), (
        "repeated labels should collapse without reordering"
    )
    overlap = row["overlap"]
    assert isinstance(overlap, list) and set(overlap) <= set(expected), (
        "overlap must come from the labels"
    )


@settings(max_examples=ENGINE_MAX_EXAMPLES, deadline=None)
@given(tiers=_PACK_TIERS, limit=_PACK_LIMITS)
def test_evaluate_pack_selects_replayable_cases_up_to_the_limit(
    tiers: list[str], limit: int | None
) -> None:
    replayable = tiers.count("replayable")

    summary = _summarize_tiers(tiers, EvalPackOptions(limit=limit))

    assert summary["skipped_label_only"] == len(tiers) - replayable, (
        "skipped rows should count only filtered label-only cases"
    )
    assert summary["n"] == (replayable if limit is None else min(limit, replayable)), (
        "the limit should cap replayable cases after filtering"
    )
