"""OpenCode repair state preserves paths supplied without file content."""

from __future__ import annotations

from pathlib import Path

import pytest

from slopgate._types import ObjectDict, object_dict_list
from slopgate.constants import BLOCK, PLATFORM_OPENCODE
from slopgate.context import HookContext, build_context
from slopgate.engine._evaluation import (
    _opencode_repair_recovery_message,
    _opencode_repair_required_finding,
    _record_opencode_repair_required,
)
from slopgate.models import RuleFinding, Severity
from slopgate.state import RepairRequiredPayload, RepairTarget


def _path_only_context(tmp_path: Path) -> tuple[HookContext, Path]:
    source_path = tmp_path / "src" / "app.py"
    source_path.parent.mkdir()
    source_path.write_text("value = 1\n", encoding="utf-8")
    context = build_context(
        {
            "cwd": str(tmp_path),
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": str(source_path)},
            "execution_outcome": "returned",
            "session_id": "session-1",
            "call_id": "call-1",
        }
    )

    return context, source_path


def _repair_required_context(
    tmp_path: Path,
    targets: list[RepairTarget],
) -> HookContext:
    context = build_context(
        {
            "cwd": str(tmp_path),
            "worktree": str(tmp_path),
            "hook_event_name": "PreToolUse",
            "tool_name": "custom_mutator",
            "tool_input": {"prompt": "retry the blocked edit"},
            "session_id": "session-1",
            "call_id": "call-1",
        }
    )
    context.state.mark_repair_required(
        "generation-test-1",
        RepairRequiredPayload(
            session_id="session-1",
            call_id="call-1",
            worktree=context.state.scope,
            targets=targets,
        ),
    )
    return context


def test_file_edited_repair_state_records_candidate_path_without_content(
    tmp_path: Path,
) -> None:
    context, source_path = _path_only_context(tmp_path)

    assert context.content_targets == [], "test must cover path-only evidence"
    assert context.candidate_paths == [str(source_path)], (
        "path-only OpenCode evidence must remain discoverable"
    )


def test_file_edited_repair_state_records_candidate_path_in_repair_state(
    tmp_path: Path,
) -> None:
    context, source_path = _path_only_context(tmp_path)

    _record_opencode_repair_required(
        context,
        [
            RuleFinding(
                rule_id="PY-AST-001",
                title="parse failure",
                severity=Severity.CRITICAL,
                decision=BLOCK,
                metadata={"path": str(source_path), "function": "parse_source"},
            )
        ],
        PLATFORM_OPENCODE,
    )

    required = context.state.get_repair_required()
    assert required is not None, "blocking findings must create repair state"
    assert required["paths"] == [str(source_path)], (
        "repair verification must receive the affected file path"
    )


def _record_nested_event_repair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[ObjectDict | None, Path]:
    worktree = tmp_path / "worktree"
    event_cwd = worktree / "packages" / "service"
    intended = event_cwd / "app.py"
    daemon_cwd = tmp_path / "daemon"
    event_cwd.mkdir(parents=True)
    daemon_cwd.mkdir()
    intended.write_text("value = 1\n", encoding="utf-8")
    (daemon_cwd / "app.py").write_text("value = 2\n", encoding="utf-8")
    monkeypatch.chdir(daemon_cwd)
    context = build_context(
        {
            "cwd": str(event_cwd),
            "worktree": str(worktree),
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": "app.py"},
            "execution_outcome": "returned",
            "session_id": "session-1",
            "call_id": "call-1",
        }
    )
    finding = RuleFinding(
        rule_id="PY-AST-001",
        title="parse failure",
        severity=Severity.CRITICAL,
        decision=BLOCK,
        metadata={"path": "app.py", "function": "parse_source"},
    )
    _record_opencode_repair_required(context, [finding], PLATFORM_OPENCODE)
    return context.state.get_repair_required(), intended


def test_repair_target_uses_nested_event_cwd_not_process_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    required, intended = _record_nested_event_repair(tmp_path, monkeypatch)

    assert required is not None, "blocking findings must create repair state"
    assert required["targets"] == [
        {
            "rule_id": "PY-AST-001",
            "path": str(intended.resolve()),
            "raw_path": "app.py",
            "function": "parse_source",
            "error": None,
        }
    ], "repair targets must resolve from the event working directory"


def _record_unverifiable_repair(
    tmp_path: Path, metadata: ObjectDict
) -> ObjectDict | None:
    context = build_context(
        {
            "cwd": str(tmp_path),
            "worktree": str(tmp_path),
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "execution_outcome": "returned",
            "session_id": "session-1",
            "call_id": "call-1",
        }
    )
    finding = RuleFinding(
        rule_id="QUALITY-POST-001",
        title="quality failure",
        severity=Severity.CRITICAL,
        decision=BLOCK,
        metadata=metadata,
    )
    _record_opencode_repair_required(context, [finding], PLATFORM_OPENCODE)
    return context.state.get_repair_required()


@pytest.mark.parametrize(
    ("metadata", "expected_error"),
    [
        pytest.param({}, "finding has no file target", id="pathless"),
        pytest.param(
            {"path": "missing.py"},
            "finding path is not an existing file",
            id="missing",
        ),
        pytest.param(
            {"path": "../outside.py"},
            "finding path is outside repository root",
            id="outside",
        ),
    ],
)
def test_unverifiable_repair_target_is_explicit_and_pending(
    tmp_path: Path, metadata: ObjectDict, expected_error: str
) -> None:
    required = _record_unverifiable_repair(tmp_path, metadata)

    assert required is not None, "unverifiable findings must remain pending"
    assert required["status"] == "REPAIR_REQUIRED", (
        "unverifiable findings must fail closed"
    )
    targets = object_dict_list(required.get("targets"))
    assert targets, "unverifiable findings must retain a causal target"
    assert targets[0]["error"] == expected_error, (
        "repair state must explain why its causal target cannot be verified"
    )


def test_repair_gate_finding_demands_stop_and_names_allowed_tools(
    tmp_path: Path,
) -> None:
    context = _repair_required_context(
        tmp_path,
        [RepairTarget("PY-CODE-013", "src/sample.py", "src/sample.py", None, None)],
    )

    finding = _opencode_repair_required_finding(context, PLATFORM_OPENCODE)

    assert finding is not None, (
        "blocked wrapper tools must raise the repair gate finding"
    )
    assert finding.message is not None, "denial must carry a message"
    message = finding.message
    assert "STOP" in message, f"protocol must open with STOP: {message}"
    assert "do not retry this blocked mutation" in message, (
        f"missing no-retry directive: {message}"
    )
    assert "equivalent retries remain blocked" in message, (
        f"missing blocked-retry statement: {message}"
    )
    assert "write, edit, apply_patch" in message, (
        f"missing allowed mutation tools: {message}"
    )
    assert "slopgate_verify_repair" in message, (
        f"missing repair verifier tool: {message}"
    )
    assert "slopgate lint check" in message, f"missing exact lint gate: {message}"


def test_repair_gate_finding_renders_causal_recovery(
    tmp_path: Path,
) -> None:
    target_path = str(tmp_path / "src" / "sample.py")
    context = _repair_required_context(
        tmp_path,
        [RepairTarget("PY-CODE-013", target_path, target_path, "sample", None)],
    )

    finding = _opencode_repair_required_finding(context, PLATFORM_OPENCODE)

    assert finding is not None, "blocked wrapper tools must raise the repair gate"
    assert finding.message is not None, "denial must carry a message"
    message = finding.message
    assert "slopgate repair status --cwd" not in message, (
        f"blocked status command must not be advertised: {message}"
    )
    assert f"read the first causal finding: PY-CODE-013 in {target_path}" in message, (
        f"missing causal finding render: {message}"
    )
    assert "slopgate repair verify --cwd" not in message, (
        f"blocked verify command must not be advertised: {message}"
    )
    assert "resolves the pending generation from repair state" in message, (
        f"registered verifier must explain generation discovery: {message}"
    )


def test_repair_gate_finding_preserves_causal_state(tmp_path: Path) -> None:
    target_path = str(tmp_path / "src" / "sample.py")
    context = _repair_required_context(
        tmp_path,
        [RepairTarget("PY-CODE-013", target_path, target_path, "sample", None)],
    )

    finding = _opencode_repair_required_finding(context, PLATFORM_OPENCODE)

    assert finding is not None, "blocked wrapper tools must raise the repair gate"
    assert finding.metadata == {
        "generation": "generation-test-1",
        "rule_ids": ["PY-CODE-013"],
        "paths": [target_path],
        "targets": [
            {
                "rule_id": "PY-CODE-013",
                "path": target_path,
                "raw_path": target_path,
                "function": "sample",
                "error": None,
            }
        ],
        "worktree": str(tmp_path),
    }, "causal metadata must be preserved for traces"


def test_repair_gate_finding_without_causal_metadata_omits_details(
    tmp_path: Path,
) -> None:
    context = _repair_required_context(tmp_path, [])

    finding = _opencode_repair_required_finding(context, PLATFORM_OPENCODE)

    assert finding is not None
    assert finding.message is not None, "denial must carry a message"
    message = finding.message
    assert "read the first causal finding: invalid or legacy repair state" in message, (
        f"missing invalid-state fallback: {message}"
    )
    assert finding.metadata == {
        "generation": "generation-test-1",
        "rule_ids": [],
        "paths": [],
        "targets": [],
        "worktree": str(tmp_path),
    }, "empty causal state must render without invented details"


_RECOVERY_PROTOCOL_FRAGMENTS = (
    "STOP: do not retry this blocked mutation",
    "equivalent retries remain blocked",
    "Recovery protocol:",
    "read the first causal finding:",
    "inspect affected files with declared read-only tools",
    "make one focused repair with an allowed mutation tool",
    "write, edit, apply_patch",
    "run slopgate_verify_repair",
    "resolves the pending generation from repair state",
    "Allowed during repair: declared read-only",
    "write/edit/apply_patch, slopgate_verify_repair, exact slopgate lint check",
    "Bash, patch, diagnostic, and wrapper-tool retries remain blocked",
)


@pytest.mark.parametrize("fragment", _RECOVERY_PROTOCOL_FRAGMENTS)
def test_engine_repair_message_preserves_recovery_protocol(fragment: str) -> None:
    message = _opencode_repair_recovery_message(
        "generation-1", "PY-CODE-013 in src/sample.py"
    )
    assert fragment in message, f"engine protocol drifted: missing {fragment!r}"
