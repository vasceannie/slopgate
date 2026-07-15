from __future__ import annotations

import json

from slopgate._types import ObjectDict, object_dict
from tests.test_engine import (
    MonkeyPatch,
    Path,
    keep_default_config,
    latest_trace_event,
    pretool_bash_payload,
    pretool_write_payload,
    write_config_from_defaults,
    write_slopgate,
    evaluate_payload,
)


def _trace_opencode_git_status(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    repo = write_slopgate(tmp_path / "repo_trace_timing")
    write_config_from_defaults(tmp_path, monkeypatch, keep_default_config)
    monkeypatch.setenv("SLOPGATE_ROOT", str(tmp_path / "vf-root"))
    _ = evaluate_payload(pretool_bash_payload(repo, "git status"), platform="opencode")


def _latest_result_has_timing(tmp_path: Path) -> bool:
    record = _latest_result_record(tmp_path)
    timing = object_dict(record.get("timing"))
    evaluation_ms = timing.get("evaluation_ms")
    rule_engine_ms = timing.get("rule_engine_ms")
    timing_contract = {
        "has_evaluation_ms": isinstance(evaluation_ms, int),
        "has_rule_engine_ms": isinstance(rule_engine_ms, int),
        "non_negative_eval": isinstance(evaluation_ms, int) and evaluation_ms >= 0,
        "non_negative_rules": isinstance(rule_engine_ms, int) and rule_engine_ms >= 0,
    }
    return timing_contract == {
        "has_evaluation_ms": True,
        "has_rule_engine_ms": True,
        "non_negative_eval": True,
        "non_negative_rules": True,
    }


def _latest_result_record(tmp_path: Path) -> ObjectDict:
    results_path = tmp_path / "vf-root" / "logs" / "results.jsonl"
    records: list[ObjectDict] = [
        object_dict(json.loads(line))
        for line in results_path.read_text(encoding="utf-8").splitlines()
    ]
    return records[-1]


def _trace_write_result(tmp_path: Path, monkeypatch: MonkeyPatch) -> ObjectDict:
    repo = write_slopgate(tmp_path / "repo_trace_recovery_schema")
    write_config_from_defaults(tmp_path, monkeypatch, keep_default_config)
    monkeypatch.setenv("SLOPGATE_ROOT", str(tmp_path / "vf-root"))
    _ = evaluate_payload(
        pretool_write_payload(repo, "src/app.py", "value = 1\n"),
        platform="opencode",
    )
    return _latest_result_record(tmp_path)


def _recovery_schema_projection(record: ObjectDict) -> ObjectDict:
    return {
        "trace_schema_version": record.get("trace_schema_version"),
        "evaluation_id_present": bool(record.get("evaluation_id")),
        "operation_id": record.get("operation_id"),
        "correlation_confidence": record.get("correlation_confidence"),
        "candidate_paths": record.get("candidate_paths"),
        "fingerprint_present": bool(record.get("attempt_fingerprint")),
        "event_outcome_present": isinstance(record.get("event_outcome"), str),
        "tool_outcome": record.get("tool_outcome"),
        "rule_response_version": record.get("rule_response_version"),
        "intervention_tags": record.get("intervention_tags"),
        "repair_plan_state": record.get("repair_plan_state"),
    }


def test_trace_records_platform_capability_and_repo_root(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    repo = write_slopgate(tmp_path / "repo_trace_capability")
    write_config_from_defaults(tmp_path, monkeypatch, keep_default_config)
    monkeypatch.setenv("SLOPGATE_ROOT", str(tmp_path / "vf-root"))

    _ = evaluate_payload(
        pretool_bash_payload(repo, "git commit -n -m skip"), platform="opencode"
    )

    record = latest_trace_event(tmp_path)
    assert record["platform_capability"] == "degraded"
    assert record["resolved_repo_root"] == str(repo.resolve())


def test_trace_records_omitted_platform_as_unknown(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    repo = write_slopgate(tmp_path / "repo_trace_unknown_platform")
    write_config_from_defaults(tmp_path, monkeypatch, keep_default_config)
    monkeypatch.setenv("SLOPGATE_ROOT", str(tmp_path / "vf-root"))

    _ = evaluate_payload(pretool_bash_payload(repo, "git status"))

    record = latest_trace_event(tmp_path)
    assert record["platform"] == "unknown", (
        "Omitted runtime platform should not be recorded as Claude provenance"
    )
    assert record["platform_source"] == "unknown", (
        "Trace metadata should expose that platform provenance was unknown"
    )
    assert record["platform_capability"] == "unknown", (
        "Unknown platform should not inherit Claude's full capability label"
    )


def test_results_trace_records_aggregate_timing_metadata(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    _trace_opencode_git_status(tmp_path, monkeypatch)
    assert _latest_result_has_timing(tmp_path), (
        "results trace should include non-negative aggregate timing metadata"
    )


def test_results_trace_records_recovery_schema_v2(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    record = _trace_write_result(tmp_path, monkeypatch)

    assert _recovery_schema_projection(record) == {
        "trace_schema_version": 2,
        "evaluation_id_present": True,
        "operation_id": None,
        "correlation_confidence": "inferred",
        "candidate_paths": ["src/app.py"],
        "fingerprint_present": True,
        "event_outcome_present": True,
        "tool_outcome": "unknown",
        "rule_response_version": "1",
        "intervention_tags": [],
        "repair_plan_state": "none",
    }, "Completed results must carry the full recovery trace schema"
