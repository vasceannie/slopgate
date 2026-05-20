from __future__ import annotations

from tests.test_engine import (
    MonkeyPatch,
    Path,
    _keep_default_config,
    _latest_trace_event,
    _pretool_bash_payload,
    _write_config_from_defaults,
    _write_quality_gate,
    evaluate_payload,
)

def test_trace_records_platform_capability_and_repo_root(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    repo = _write_quality_gate(tmp_path / "repo_trace_capability")
    _write_config_from_defaults(tmp_path, monkeypatch, _keep_default_config)
    monkeypatch.setenv("VIBEFORCER_ROOT", str(tmp_path / "vf-root"))

    _ = evaluate_payload(
        _pretool_bash_payload(repo, "git commit -n -m skip"), platform="opencode"
    )

    record = _latest_trace_event(tmp_path)
    assert record["platform_capability"] == "degraded"
    assert record["resolved_repo_root"] == str(repo.resolve())
