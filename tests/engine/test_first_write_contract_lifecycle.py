from __future__ import annotations

from pathlib import Path

import pytest

from slopgate.engine import evaluate_payload
from tests.first_write_contract_support import (
    RULE_ID,
    EditCase,
    configure_contract_test,
    edit_payload,
    evaluate_edit_cases,
    record_contract,
)


def test_complete_contract_authorizes_one_mutation_then_is_consumed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, _trace_dir = configure_contract_test(tmp_path, monkeypatch, action="deny")
    assert record_contract(repo, capsys) == 0, "Complete contract should record"
    authorized, completed, next_attempt = evaluate_edit_cases(
        repo,
        EditCase(),
        EditCase(event="PostToolUse"),
        EditCase(),
    )

    assert all(item.rule_id != RULE_ID for item in authorized.findings), (
        "Complete contract should authorize its exact first mutation"
    )
    assert all(item.rule_id != RULE_ID for item in completed.findings), (
        "Post-tool consumption should not emit a blocking finding"
    )
    finding = next(item for item in next_attempt.findings if item.rule_id == RULE_ID)
    assert finding.decision == "deny", (
        "Consumed contract should not authorize a second mutation"
    )


def test_multi_target_block_denies_each_uncovered_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, _trace_dir = configure_contract_test(tmp_path, monkeypatch, action="deny")
    assert record_contract(repo, capsys, target="src/one.py") == 0, (
        "Covered target contract should record"
    )
    payload = edit_payload(repo, EditCase(target="src/one.py"))
    payload["tool_input"] = {
        "edits": [
            {"file_path": "src/one.py", "new_string": "one"},
            {"file_path": "src/two.py", "new_string": "two"},
        ]
    }

    blocked = evaluate_payload(payload, platform="claude")
    blocked_finding = next(
        item
        for item in blocked.findings
        if item.rule_id == RULE_ID and item.metadata.get("contract_status") == "missing"
    )
    assert blocked_finding.decision == "deny", (
        "Each uncovered multi-edit target should block independently"
    )


def test_multi_target_block_leaves_covered_contract_ready(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, _trace_dir = configure_contract_test(tmp_path, monkeypatch, action="deny")
    assert record_contract(repo, capsys, target="src/one.py") == 0, (
        "Covered target contract should record"
    )
    payload = edit_payload(repo, EditCase(target="src/one.py"))
    payload["tool_input"] = {
        "edits": [
            {"file_path": "src/one.py", "new_string": "one"},
            {"file_path": "src/two.py", "new_string": "two"},
        ]
    }

    _ = evaluate_payload(payload, platform="claude")
    later_single = evaluate_edit_cases(repo, EditCase(target="src/one.py"))[0]

    assert RULE_ID not in {item.rule_id for item in later_single.findings}, (
        "A blocked multi-edit should leave covered contracts ready"
    )


def test_contract_does_not_leak_across_sessions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, _trace_dir = configure_contract_test(tmp_path, monkeypatch, action="deny")
    assert record_contract(repo, capsys) == 0, "Matching contract should record"
    other_session = evaluate_edit_cases(repo, EditCase(session_id="session-b"))[0]

    session_finding = next(
        item for item in other_session.findings if item.rule_id == RULE_ID
    )

    assert session_finding.decision == "deny", "Contracts must not leak across sessions"


def test_contract_does_not_leak_across_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, _trace_dir = configure_contract_test(tmp_path, monkeypatch, action="deny")
    assert record_contract(repo, capsys) == 0, "Matching contract should record"
    other_path = evaluate_edit_cases(repo, EditCase(target="src/other.py"))[0]

    path_finding = next(item for item in other_path.findings if item.rule_id == RULE_ID)

    assert path_finding.decision == "deny", "Contracts must not leak across targets"


def test_contract_requires_exact_operation_without_consuming_match(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo, _trace_dir = configure_contract_test(tmp_path, monkeypatch, action="deny")
    assert record_contract(repo, capsys) == 0, "Matching contract should record"
    other_operation, authorized = evaluate_edit_cases(
        repo, EditCase(tool_name="Write"), EditCase()
    )

    operation_finding = next(
        item for item in other_operation.findings if item.rule_id == RULE_ID
    )

    assert operation_finding.metadata["contract_status"] == "operation", (
        "Contracts must match the exact normalized operation"
    )
    assert all(item.rule_id != RULE_ID for item in authorized.findings), (
        "Unrelated misses should not consume the matching contract"
    )
