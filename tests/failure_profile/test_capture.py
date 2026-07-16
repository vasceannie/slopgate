from __future__ import annotations

import json
from pathlib import Path

import pytest

from slopgate.engine import evaluate_payload
from tests.failure_profile.support import (
    FIRST_WRITE_RULE_ID,
    PROFILE_RULE_ID,
    ProfileRepoOptions,
    configure_profile_repo,
    configure_profile_worktree,
    edit_payload,
    profile_entries,
    profile_payloads,
    profile_scope_ids,
    profile_storage_keys,
)


PROHIBITED_KEYS = {
    "prompt",
    "patch",
    "tool_input",
    "proposed_content",
    "content",
    "source",
    "snippet",
    "path",
    "raw_path",
    "session_id",
}


def test_repo_opt_in_records_only_allowed_aggregate_dimensions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, trace_dir = configure_profile_repo(
        tmp_path, monkeypatch, ProfileRepoOptions(first_write_action="deny")
    )

    result = evaluate_payload(edit_payload(repo), platform="claude")

    entries = profile_entries(trace_dir)
    entry = entries[0]
    assert PROFILE_RULE_ID in {finding.rule_id for finding in result.findings}, (
        "The real engine path should produce the profiled denial"
    )
    assert {item["rule_id"] for item in entries} == {PROFILE_RULE_ID}, (
        "Feedback-loop meta rules should not become circular preflight risks"
    )
    assert set(entry) == {
        "rule_id",
        "path_role",
        "language",
        "platform",
        "model_identifier",
        "resolution_outcome",
        "daily_counts",
    }, "Stored entries should contain only approved aggregate dimensions and counts"
    assert entry["path_role"] == "source", "Raw source paths must reduce to a role"
    assert entry["language"] == "python", "Language should be aggregated explicitly"
    assert entry["platform"] == "claude", "Platform should be aggregated explicitly"
    assert entry["model_identifier"] == "gpt-5.6-sol", (
        "Present model identifiers should be retained as an approved dimension"
    )
    assert entry["resolution_outcome"] == "blocked", (
        "Denied findings should record a blocked resolution outcome"
    )


def test_profile_storage_recursively_excludes_prohibited_keys(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, trace_dir = configure_profile_repo(tmp_path, monkeypatch)

    _ = evaluate_payload(edit_payload(repo), platform="claude")

    assert PROHIBITED_KEYS.isdisjoint(profile_storage_keys(trace_dir)), (
        "Prohibited content keys must be absent recursively"
    )


def test_profile_storage_excludes_raw_sensitive_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, trace_dir = configure_profile_repo(tmp_path, monkeypatch)

    _ = evaluate_payload(edit_payload(repo), platform="claude")

    stored_text = json.dumps(profile_payloads(trace_dir), sort_keys=True)
    assert not any(
        value in stored_text for value in (str(repo), "session-a", "PROFILE_TRIGGER")
    ), "Stored aggregates must not contain raw paths, sessions, or proposed content"


def test_profile_is_off_by_default_and_does_not_write_storage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, trace_dir = configure_profile_repo(
        tmp_path, monkeypatch, ProfileRepoOptions(enabled=False)
    )

    _ = evaluate_payload(edit_payload(repo), platform="claude")

    assert not list((trace_dir / "failure-profiles").glob("*.json")), (
        "Existing installs should remain profile-off"
    )


def test_worktrees_use_distinct_profile_scopes_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, trace_dir = configure_profile_repo(tmp_path, monkeypatch)
    worktree = configure_profile_worktree(tmp_path, repo)

    _ = evaluate_payload(edit_payload(repo, session_id="main"), platform="claude")
    _ = evaluate_payload(edit_payload(worktree, session_id="branch"), platform="claude")

    scopes = profile_scope_ids(trace_dir)
    assert len(scopes) == 2, "Main checkout and worktree should not share aggregates"


def test_successful_retry_records_resolved_outcome(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, trace_dir = configure_profile_repo(tmp_path, monkeypatch)
    denied = edit_payload(repo)

    _ = evaluate_payload(denied, platform="claude")
    _ = evaluate_payload(denied, platform="claude")
    _ = evaluate_payload(
        edit_payload(repo, content="safe replacement"), platform="claude"
    )

    outcomes = {item["resolution_outcome"] for item in profile_entries(trace_dir)}
    assert outcomes == {"blocked", "resolved"}, (
        "Repeated denials followed by a clean mutation should record resolution"
    )


def test_profile_never_captures_or_steers_outside_repo_strict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo, trace_dir = configure_profile_repo(
        tmp_path,
        monkeypatch,
        ProfileRepoOptions(strict=False, first_write_action="context"),
    )

    result = evaluate_payload(edit_payload(repo), platform="claude")

    assert FIRST_WRITE_RULE_ID not in {
        finding.rule_id for finding in result.findings
    }, "Repo-relaxed evaluation must not run first-write steering"
    assert not list((trace_dir / "failure-profiles").glob("*.json")), (
        "Repo-relaxed evaluation must not capture profiles"
    )
