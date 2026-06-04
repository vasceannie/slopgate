"""Integration references for shared adapter payload normalization helpers."""

from __future__ import annotations

from slopgate._types import object_dict
from slopgate.adapters import _payload_fields as payload_fields
from slopgate.adapters.cursor_output import (
    CursorRenderRequest,
    cursor_render_request_from_call,
    render_cursor_output,
)
from slopgate.adapters.cursor import CursorAdapter
from slopgate.models import RuleFinding


def test_merge_session_id_populates_canonical_payload() -> None:
    canonical = object_dict({})
    payload_fields.merge_session_id(
        {"sessionId": "abc", "conversation_id": "ignored"},
        canonical,
    )
    assert canonical["session_id"] == "abc"


def test_merge_cwd_populates_canonical_payload() -> None:
    canonical = object_dict({})
    payload_fields.merge_cwd({"directory": "/tmp/repo"}, canonical, extra_keys=("directory",))
    assert canonical["cwd"] == "/tmp/repo"


def test_sync_tool_result_fields_aliases_responses() -> None:
    canonical = object_dict({"tool_response": {"ok": True}})
    payload_fields.sync_tool_result_fields(canonical)
    assert canonical["tool_result"] == {"ok": True}


def test_merge_standard_session_fields_via_adapter_helpers() -> None:
    canonical = object_dict({})
    payload_fields.merge_standard_session_fields(
        {"session_id": "sess-1", "cwd": "/tmp"},
        canonical,
    )
    assert canonical["session_id"] == "sess-1"
    assert canonical["cwd"] == "/tmp"


def test_cursor_output_helpers_are_referenced() -> None:
    adapter = CursorAdapter()
    finding = RuleFinding(
        rule_id="TEST-CTX",
        title="Context",
        severity="medium",
        message="reminder",
    )
    request = CursorRenderRequest(
        event_name="UserPromptSubmit",
        findings=[finding],
        context="follow up",
        updated_input={},
        decision=None,
    )
    assert render_cursor_output(adapter, request) == {
        "continue": True,
        "user_message": "follow up",
    }
    assert callable(cursor_render_request_from_call)
