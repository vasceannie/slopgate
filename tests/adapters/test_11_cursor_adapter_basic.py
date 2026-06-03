from __future__ import annotations

from typing import cast

from tests.test_adapters import (
    CursorAdapter,
    RuleFinding,
    Severity,
    get_adapter,
    require_rendered,
)
from vibeforcer._types import ObjectDict
from vibeforcer.constants import BLOCK, DENY, POST_TOOL_USE, PRE_TOOL_USE


def test_cursor_adapter_registry_name() -> None:
    adapter = CursorAdapter()
    assert adapter.name == "cursor"


def test_cursor_adapter_normalizes_shell_event() -> None:
    adapter = CursorAdapter()
    normalized = adapter.normalize_payload(
        {
            "hook_event_name": "beforeShellExecution",
            "command": "echo hi",
            "cwd": "/tmp/project",
        }
    )
    assert {
        "hook_event_name": normalized["hook_event_name"],
        "tool_name": normalized["tool_name"],
        "command": normalized["tool_input"]["command"],
        "cwd": normalized["cwd"],
    } == {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "command": "echo hi",
        "cwd": "/tmp/project",
    }


def test_cursor_adapter_normalizes_before_shell_execution_payload() -> None:
    normalized = get_adapter("cursor").normalize_payload(
        {
            "hook_event_name": "beforeShellExecution",
            "command": "python -m pytest -q",
            "cwd": "/repo",
            "conversation_id": "conv-1",
        }
    )
    assert {
        "hook_event_name": normalized["hook_event_name"],
        "tool_name": normalized["tool_name"],
        "tool_input": normalized["tool_input"],
        "cwd": normalized["cwd"],
        "session_id": normalized["session_id"],
    } == {
        "hook_event_name": PRE_TOOL_USE,
        "tool_name": "Bash",
        "tool_input": {"command": "python -m pytest -q"},
        "cwd": "/repo",
        "session_id": "conv-1",
    }


def test_cursor_adapter_normalizes_after_file_edit_for_post_tool_backstop() -> None:
    normalized = get_adapter("cursor").normalize_payload(
        {
            "hook_event_name": "afterFileEdit",
            "file_path": "/repo/src/app.py",
            "edits": [{"old_string": "x", "new_string": "y"}],
            "conversation_id": "conv-2",
        }
    )
    tool_input = cast(ObjectDict, normalized["tool_input"])
    tool_response = cast(ObjectDict, normalized["tool_response"])
    assert {
        "hook_event_name": normalized["hook_event_name"],
        "tool_name": normalized["tool_name"],
        "file_path": tool_input["file_path"],
        "response_path": tool_response["file_path"],
    } == {
        "hook_event_name": POST_TOOL_USE,
        "tool_name": "Write",
        "file_path": "/repo/src/app.py",
        "response_path": "/repo/src/app.py",
    }


def test_cursor_adapter_renders_deny_output() -> None:
    adapter = CursorAdapter()
    finding = RuleFinding(
        rule_id="CURSOR-001",
        title="blocked",
        severity=Severity.HIGH,
        decision="deny",
        message="cursor hook denied",
    )
    output = require_rendered(
        adapter.render_output("PreToolUse", [finding], decision="deny"),
    )
    assert {
        "permission": output["permission"],
        "user_message": output["user_message"],
        "agent_message": output["agent_message"],
    } == {
        "permission": "deny",
        "user_message": "[CURSOR-001 | HIGH] cursor hook denied",
        "agent_message": "[CURSOR-001 | HIGH] cursor hook denied",
    }


def test_cursor_adapter_renders_pretool_deny_in_native_schema() -> None:
    finding = RuleFinding(
        rule_id="TEST-001",
        title="blocked",
        severity=Severity.HIGH,
        decision=DENY,
        message="Nope goblin.",
        additional_context="Use the safer path.",
    )
    output = require_rendered(
        get_adapter("cursor").render_output(
            PRE_TOOL_USE,
            [finding],
            decision=DENY,
            context="Use the safer path.",
        )
    )
    assert output == {
        "permission": "deny",
        "user_message": "[TEST-001 | HIGH] Nope goblin.",
        "agent_message": "[TEST-001 | HIGH] Nope goblin.\n\nUse the safer path.",
    }


def test_cursor_adapter_renders_stop_block_as_followup() -> None:
    finding = RuleFinding(
        rule_id="STOP-001",
        title="continue",
        severity=Severity.HIGH,
        decision=BLOCK,
        message="Quality gate still failing.",
    )
    output = require_rendered(
        get_adapter("cursor").render_output("Stop", [finding], decision=BLOCK),
    )
    assert output == {"followup_message": "[STOP-001 | HIGH] Quality gate still failing."}
