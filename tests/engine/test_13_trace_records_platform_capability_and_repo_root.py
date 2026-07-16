from __future__ import annotations

import json

from tests.test_engine import (
    MonkeyPatch,
    Path,
    keep_default_config,
    latest_trace_event,
    pretool_bash_payload,
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
    results_path = tmp_path / "vf-root" / "logs" / "results.jsonl"
    records = [
        json.loads(line)
        for line in results_path.read_text(encoding="utf-8").splitlines()
    ]
    timing = records[-1]["timing"]
    timing_contract = {
        "has_evaluation_ms": isinstance(timing["evaluation_ms"], int),
        "has_rule_engine_ms": isinstance(timing["rule_engine_ms"], int),
        "non_negative_eval": timing["evaluation_ms"] >= 0,
        "non_negative_rules": timing["rule_engine_ms"] >= 0,
    }
    return timing_contract == {
        "has_evaluation_ms": True,
        "has_rule_engine_ms": True,
        "non_negative_eval": True,
        "non_negative_rules": True,
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


def test_pi_platform_capability_is_partial() -> None:
    from slopgate.engine._runner import platform_capability

    capability, limitation = platform_capability("pi")

    assert capability == "partial", "Pi must not inherit Claude's full capability label"
    assert limitation, "Partial capability labels should explain the platform limit"


def test_results_trace_records_aggregate_timing_metadata(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    _trace_opencode_git_status(tmp_path, monkeypatch)
    assert _latest_result_has_timing(tmp_path), (
        "results trace should include non-negative aggregate timing metadata"
    )
