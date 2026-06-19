"""Integration references for shared adapter payload normalization helpers."""

from __future__ import annotations
from hypothesis import given, strategies

from slopgate._types import object_dict
from slopgate.adapters import _payload_fields
from slopgate.adapters._session_identity import (
    first_nested_identity_value,
    identity_object_sources,
)
from slopgate.adapters._payload_fields import (
    canonical_event_name,
    canonical_payload_with_event,
)
from slopgate.adapters.codex import CodexAdapter
from slopgate.adapters.cursor_output import (
    CursorRenderRequest,
    cursor_render_request_from_call,
    render_cursor_output,
)
from slopgate.adapters.cursor import CursorAdapter
from slopgate.models import RuleFinding, Severity


def test_merge_session_id_populates_canonical_payload() -> None:
    canonical = object_dict({})
    _payload_fields.merge_session_id(
        {"sessionId": "abc", "conversation_id": "ignored"}, canonical
    )
    assert canonical["session_id"] == "abc"


def test_merge_cwd_populates_canonical_payload() -> None:
    canonical = object_dict({})
    _payload_fields.merge_cwd(
        {"directory": "/tmp/repo"}, canonical, extra_keys=("directory",)
    )
    assert canonical["cwd"] == "/tmp/repo"


def test_sync_tool_result_fields_aliases_responses() -> None:
    canonical = object_dict({"tool_response": {"ok": True}})
    _payload_fields.sync_tool_result_fields(canonical)
    assert canonical["tool_result"] == {"ok": True}


def test_merge_standard_session_fields_via_adapter_helpers() -> None:
    canonical = object_dict({})
    _payload_fields.merge_standard_session_fields(
        {"session_id": "sess-1", "cwd": "/tmp"}, canonical
    )
    assert canonical["session_id"] == "sess-1"
    assert canonical["cwd"] == "/tmp"


def test_canonical_event_name_feeds_real_adapter_normalization() -> None:
    raw = {"hookEventName": "tool-call", "toolName": "write"}

    assert canonical_event_name(
        raw, {"PreToolUse"}, {"toolcall": "PreToolUse"}
    ) == "PreToolUse"
    assert CodexAdapter().normalize_payload({"hookEventName": "session-start"})[
        "hook_event_name"
    ] == "SessionStart"


def test_canonical_payload_with_event_feeds_adapter_normalization() -> None:
    assert canonical_payload_with_event({"cwd": "/repo"}, "SessionStart") == {
        "cwd": "/repo",
        "hook_event_name": "SessionStart",
    }


@given(event=strategies.sampled_from(("PreToolUse", "pre-tool-use", "unknown")))
def test_canonical_event_name_preserves_known_and_alias_invariants(event: str) -> None:
    canonical = canonical_event_name(
        {"hookEventName": event}, {"PreToolUse"}, {"pretooluse": "PreToolUse"}
    )

    assert canonical == ("PreToolUse" if event != "unknown" else "unknown"), (
        "canonical_event_name should preserve known events and map configured aliases"
    )


def test_codex_identity_helpers_feed_real_adapter_normalization() -> None:
    raw = {"params": {"thread": {"id": " thread-1 ", "name": "Build fix"}}}
    sources = identity_object_sources(raw, ("params",))
    thread_source = object_dict(sources[0].get("thread"))
    session_id = first_nested_identity_value(
        (thread_source,),
        ("id",),
        metric_name="test.identity.integration",
    )
    canonical = CodexAdapter().normalize_payload(
        {
            "method": "thread/started",
            "params": {"thread": {"id": session_id, "name": "Build fix"}},
        }
    )

    assert canonical["session_id"] == "thread-1", (
        "Codex normalization should consume trimmed identity helper output"
    )
    assert canonical["session_title"] == "Build fix", (
        "Codex normalization should preserve title from shared identity sources"
    )


def test_cursor_output_helpers_are_referenced() -> None:
    adapter = CursorAdapter()
    finding = RuleFinding(
        rule_id="TEST-CTX",
        title="Context",
        severity=Severity.MEDIUM,
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
