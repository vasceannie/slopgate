from __future__ import annotations

import json
from pathlib import Path

import pytest

from slopgate._types import object_dict
from slopgate.engine import evaluate_payload
from tests.first_write_contract_support import (
    RULE_ID,
    BlockingCase,
    configure_contract_test,
    edit_payload,
)


BLOCKING_CASES = (
    BlockingCase("claude", "PreToolUse", "permissionDecision", "deny"),
    BlockingCase("opencode", "PreToolUse", "action", "block"),
    BlockingCase("opencode", "PermissionRequest", "action", "block"),
)


def test_default_shadow_traces_missing_contract_without_hook_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, trace_dir = configure_contract_test(tmp_path, monkeypatch)

    result = evaluate_payload(edit_payload(repo), platform="claude")

    finding = next(item for item in result.findings if item.rule_id == RULE_ID)
    traced = _traced_rule(trace_dir)
    assert finding.decision is None, "Shadow rollout should not block"
    assert finding.additional_context is None, "Shadow rollout should stay silent"
    assert result.output is None, "Shadow rollout should not emit adapter output"
    assert traced["rule_id"] == RULE_ID, "Shadow rollout should remain observable"


def test_advisory_emits_target_specific_native_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, _trace_dir = configure_contract_test(tmp_path, monkeypatch, action="context")

    result = evaluate_payload(edit_payload(repo), platform="opencode")

    finding = next(item for item in result.findings if item.rule_id == RULE_ID)
    output = object_dict(result.output)
    target = str((repo / "src/app.py").resolve())
    assert finding.decision is None, "Advisory rollout should not block"
    assert finding.metadata["missing_fields"], "Advisory should identify missing fields"
    assert finding.metadata["target"] == target, "Advisory should identify its target"
    assert output["action"] == "context", (
        "OpenCode should receive native context output"
    )
    assert target in str(output["context"]), (
        "Advisory context should be target-specific"
    )


def test_advisory_exposes_record_command_for_the_normalized_session_and_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, _trace_dir = configure_contract_test(tmp_path, monkeypatch, action="context")

    result = evaluate_payload(edit_payload(repo), platform="opencode")

    finding = next(item for item in result.findings if item.rule_id == RULE_ID)
    target = str((repo / "src/app.py").resolve())
    assert finding.metadata["record_command"] == [
        "slopgate",
        "contract",
        "record",
        "--session-id",
        "session-a",
        "--target",
        target,
        "--operation",
        "edit",
    ], "Advisory metadata should provide a usable record-command prefix"


@pytest.mark.parametrize(
    "case",
    BLOCKING_CASES,
    ids=("claude_pre", "opencode_pre", "opencode_permission"),
)
def test_blocking_denies_only_supported_pre_edit_surfaces(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: BlockingCase,
) -> None:
    repo, _trace_dir = configure_contract_test(tmp_path, monkeypatch, action="deny")
    payload = edit_payload(repo)
    payload["hook_event_name"] = case.event

    result = evaluate_payload(payload, platform=case.platform)

    output = object_dict(result.output)
    if case.platform == "claude":
        output = object_dict(output.get("hookSpecificOutput"))
    assert output[case.expected_key] == case.expected_value, (
        "Blocking rollout should use the platform-native pre-edit denial"
    )


def test_disabled_surface_skips_contract_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, _trace_dir = configure_contract_test(tmp_path, monkeypatch, enabled=False)

    result = evaluate_payload(edit_payload(repo), platform="claude")

    assert all(item.rule_id != RULE_ID for item in result.findings), (
        "Disabled enforcement should skip contract observation"
    )


def test_blocking_surface_does_not_deny_post_tool_events(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, _trace_dir = configure_contract_test(tmp_path, monkeypatch, action="deny")
    payload = edit_payload(repo)
    payload["hook_event_name"] = "PostToolUse"

    result = evaluate_payload(payload, platform="opencode")

    assert all(item.rule_id != RULE_ID for item in result.findings), (
        "Post-tool contract finalization should never hard-block"
    )


def _traced_rule(trace_dir: Path) -> dict[str, object]:
    traces = (trace_dir / "rules.jsonl").read_text(encoding="utf-8").splitlines()
    traced = next(
        object_dict(json.loads(line))
        for line in traces
        if object_dict(json.loads(line)).get("rule_id") == RULE_ID
    )
    return traced
