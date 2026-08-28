"""OpenCode repair state preserves paths supplied without file content."""

from __future__ import annotations

from pathlib import Path

import pytest

from slopgate.constants import BLOCK, PLATFORM_OPENCODE
from slopgate.context import HookContext, build_context
from slopgate.engine._evaluation import (
    _opencode_repair_recovery_message,
    _opencode_repair_required_finding,
    _record_opencode_repair_required,
)
from slopgate.models import RuleFinding, Severity
from slopgate.resources import resource_path
from slopgate.state import RepairRequiredPayload


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
    rule_ids: list[str],
    paths: list[str],
) -> HookContext:
    context = build_context(
        {
            "cwd": str(tmp_path),
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
            rule_ids=rule_ids,
            paths=paths,
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
            )
        ],
        PLATFORM_OPENCODE,
    )

    required = context.state.get_repair_required()
    assert required is not None, "blocking findings must create repair state"
    assert required["paths"] == [str(source_path)], (
        "repair verification must receive the affected file path"
    )


def test_repair_gate_finding_demands_stop_and_names_allowed_tools(
    tmp_path: Path,
) -> None:
    context = _repair_required_context(
        tmp_path,
        ["PY-CODE-013"],
        ["src/sample.py"],
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


def test_repair_gate_finding_renders_exact_repair_cli_and_causal_state(
    tmp_path: Path,
) -> None:
    context = _repair_required_context(
        tmp_path,
        ["PY-CODE-013"],
        [str(tmp_path / "src" / "sample.py")],
    )

    finding = _opencode_repair_required_finding(context, PLATFORM_OPENCODE)

    assert finding is not None, (
        "blocked wrapper tools must raise the repair gate finding"
    )
    assert finding.message is not None, "denial must carry a message"
    message = finding.message
    assert "slopgate repair status --cwd" not in message, (
        f"blocked status command must not be advertised: {message}"
    )
    assert (
        "read the first causal finding: PY-CODE-013 in "
        + str(tmp_path / "src" / "sample.py")
        in message
    ), f"missing causal finding render: {message}"
    assert "slopgate repair verify --cwd" not in message, (
        f"blocked verify command must not be advertised: {message}"
    )
    assert "resolves the pending generation from repair state" in message, (
        f"registered verifier must explain generation discovery: {message}"
    )
    assert finding.metadata == {
        "generation": "generation-test-1",
        "rule_ids": ["PY-CODE-013"],
        "paths": [str(tmp_path / "src" / "sample.py")],
    }, "causal metadata must be preserved for traces"


def test_repair_gate_finding_without_causal_metadata_omits_details(
    tmp_path: Path,
) -> None:
    context = _repair_required_context(
        tmp_path,
        [],
        [],
    )

    finding = _opencode_repair_required_finding(context, PLATFORM_OPENCODE)

    assert finding is not None
    assert finding.message is not None, "denial must carry a message"
    message = finding.message
    assert "read the first causal finding: the repair status output" in message, (
        f"missing status-output fallback: {message}"
    )
    assert finding.metadata == {
        "generation": "generation-test-1",
        "rule_ids": [],
        "paths": [],
    }, "empty causal state must render without invented details"

# Recovery-protocol drift guards are appended below.

_RECOVERY_PROTOCOL_FRAGMENTS: tuple[str, ...] = (
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
def test_recovery_protocol_fragment_is_in_engine_message(fragment: str) -> None:
    message = _opencode_repair_recovery_message(
        "generation-1",
        "PY-CODE-013 in src/sample.py",
    )

    assert fragment in message, f"engine protocol drifted: missing {fragment!r}"


@pytest.mark.parametrize("fragment", _RECOVERY_PROTOCOL_FRAGMENTS)
def test_recovery_protocol_fragment_is_in_plugin_source(fragment: str) -> None:
    plugin_source = resource_path("opencode_plugin.ts").read_text(encoding="utf-8")

    assert fragment in plugin_source, f"plugin protocol drifted: missing {fragment!r}"
