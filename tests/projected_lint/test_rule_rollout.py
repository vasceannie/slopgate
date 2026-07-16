from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from slopgate._types import object_dict
from slopgate.engine import evaluate_payload
from tests.projected_lint.support import (
    BAD_TEST,
    RULE_ID,
    BlockingCase,
    WriteCase,
    configure_rollout,
    edit_payload,
    native_blocking_output,
    shell_append_payload,
    traced_projected_rule,
    write_payload,
)


BLOCKING_CASES = (
    BlockingCase(
        "claude", "PreToolUse", "hookSpecificOutput", "permissionDecision", "deny"
    ),
    BlockingCase("opencode", "PreToolUse", "", "action", "block"),
    BlockingCase("opencode", "PermissionRequest", "", "action", "block"),
)


def test_default_shadow_traces_projected_failure_without_hook_output(
    projected_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trace_dir = configure_rollout(tmp_path, monkeypatch)

    result = evaluate_payload(
        write_payload(projected_repo, BAD_TEST, WriteCase(target="tests/test_app.py")),
        platform="claude",
    )

    finding = next(item for item in result.findings if item.rule_id == RULE_ID)
    traced = traced_projected_rule(trace_dir)
    assert finding.decision is None, "Shadow rollout should not block"
    assert finding.additional_context is None, "Shadow rollout should stay silent"
    assert result.output is None, "Shadow rollout should not emit adapter output"
    assert traced["rule_id"] == RULE_ID, "Shadow finding should remain traceable"


def test_advisory_uses_platform_native_context(
    projected_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = configure_rollout(tmp_path, monkeypatch, action="context")

    result = evaluate_payload(
        write_payload(projected_repo, BAD_TEST, WriteCase(target="tests/test_app.py")),
        platform="opencode",
    )

    output = object_dict(result.output)
    assert output["action"] == "context", "OpenCode should receive native context"
    assert RULE_ID in str(output["context"]), "Context should name projected lint"


@pytest.mark.parametrize(
    "case",
    [pytest.param(case, id=f"{case.platform}-{case.event}") for case in BLOCKING_CASES],
)
def test_blocking_uses_platform_native_pre_edit_denial(
    projected_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    case: BlockingCase,
) -> None:
    _ = configure_rollout(tmp_path, monkeypatch, action="deny")
    payload = write_payload(
        projected_repo,
        BAD_TEST,
        WriteCase(event=case.event, target="tests/test_app.py"),
    )

    result = evaluate_payload(payload, platform=case.platform)

    output = native_blocking_output(result.output, case)
    assert output[case.decision_key] == case.expected, (
        "Blocking rollout should use the platform-native denial"
    )


def test_incomplete_shell_write_remains_advisory_in_blocking_rollout(
    projected_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = configure_rollout(tmp_path, monkeypatch, action="deny")

    result = evaluate_payload(shell_append_payload(projected_repo), platform="opencode")

    finding = next(item for item in result.findings if item.rule_id == RULE_ID)
    output = object_dict(result.output)
    assert finding.decision is None, "Incomplete shell content must never block"
    assert finding.metadata["skip_reason"] == "incomplete_shell_content", (
        "Skip metadata should explain why projection was unsafe"
    )
    assert output["action"] == "context", "Unsafe projection should remain advisory"


def test_pre_edit_rule_does_not_mutate_real_repo(
    projected_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = configure_rollout(tmp_path, monkeypatch, action="deny")
    original = (projected_repo / "src/app.py").read_text(encoding="utf-8")

    _ = evaluate_payload(edit_payload(projected_repo), platform="claude")

    assert (projected_repo / "src/app.py").read_text(encoding="utf-8") == original, (
        "Projected lint must never mutate the real repository"
    )


def test_blocking_denial_restores_paths_and_cleans_overlay(
    projected_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = configure_rollout(tmp_path, monkeypatch, action="deny")
    overlay_parent = tmp_path / "overlays"
    overlay_parent.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(overlay_parent))

    result = evaluate_payload(
        write_payload(projected_repo, BAD_TEST, WriteCase(target="tests/test_app.py")),
        platform="claude",
    )

    finding = next(item for item in result.findings if item.rule_id == RULE_ID)
    assert finding.metadata["paths"] == ["tests/test_app.py"], (
        "Projected findings should restore real repository-relative paths"
    )
    assert "slopgate-projected-lint" not in str(finding.metadata), (
        "Projected metadata should not leak temporary overlay paths"
    )
    assert list(overlay_parent.iterdir()) == [], (
        "Blocking denial should clean the temporary overlay"
    )


def test_disabled_projected_surface_rolls_back_independently(
    projected_repo: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _ = configure_rollout(tmp_path, monkeypatch, enabled=False)

    result = evaluate_payload(
        write_payload(projected_repo, BAD_TEST, WriteCase(target="tests/test_app.py")),
        platform="claude",
    )

    assert all(item.rule_id != RULE_ID for item in result.findings), (
        "Projected lint should be independently disableable"
    )
