from __future__ import annotations

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
