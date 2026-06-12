from __future__ import annotations

from hypothesis import given, strategies

from dashboard.scripts.build_standalone.projection import (
    SlopgateConfig,
    classify,
    format_item,
)

SHORT_TEXT = strategies.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789_-", max_size=24
)


def test_slopgate_config_shape_exposes_dashboard_config_keys() -> None:
    assert set(SlopgateConfig.__annotations__) == {
        "enabled_rules",
        "regex_rules",
        "skip_paths",
    }


def test_classify_event_record_returns_events() -> None:
    record: dict[str, object] = {"event_name": "PostToolUse", "session_id": "session-1"}

    assert classify(record) == "events"


def test_format_item_event_filters_dashboard_fields() -> None:
    record: dict[str, object] = {
        "timestamp": "2026-06-11T00:00:00+00:00",
        "platform": "opencode",
        "event_name": "PostToolUse",
        "session_id": "session-1",
        "tool_name": "bash",
        "candidate_paths": ["src/app.py", 7],
        "languages": ["python", None],
        "command": "pytest",
        "tool_output": "ok",
        "ignored": "not projected",
    }

    assert format_item(record) == {
        "timestamp": "2026-06-11T00:00:00+00:00",
        "platform": "opencode",
        "event_name": "PostToolUse",
        "session_id": "session-1",
        "tool_name": "bash",
        "candidate_paths": ["src/app.py"],
        "languages": ["python"],
        "model": None,
        "provider": None,
        "command": "pytest",
        "tool_output": "ok",
    }


def test_integration_projection_pipeline_buckets_formatted_events_with_classify() -> (
    None
):
    record: dict[str, object] = {
        "timestamp": "2026-06-11T00:00:00+00:00",
        "event_name": "PostToolUse",
        "session_id": "session-1",
    }

    assert classify(format_item(record) or {}) == "events"


@given(event_name=SHORT_TEXT, session_id=SHORT_TEXT)
def test_classify_event_record_returns_events_property(
    event_name: str, session_id: str
) -> None:
    record: dict[str, object] = {"event_name": event_name, "session_id": session_id}

    assert classify(record) == "events"


@given(command=SHORT_TEXT, tool_output=SHORT_TEXT)
def test_format_item_event_preserves_trimmed_text_property(
    command: str, tool_output: str
) -> None:
    record: dict[str, object] = {
        "event_name": "PostToolUse",
        "session_id": "session-1",
        "command": command,
        "tool_output": tool_output,
    }

    assert format_item(record) == {
        "timestamp": "",
        "platform": "claude",
        "event_name": "PostToolUse",
        "session_id": "session-1",
        "tool_name": "",
        "candidate_paths": [],
        "languages": [],
        "model": None,
        "provider": None,
        "command": command,
        "tool_output": tool_output,
    }
