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
        "enabled_cli_rules",
        "rule_surfaces",
        "rule_counterparts",
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
        "tool_input": None,
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
        "tool_input": None,
        "platform_source": "explicit",
    }


def test_format_item_event_preserves_apply_patch_tool_input() -> None:
    patch_text = "*** Begin Patch\n*** Update File: app.py\n-old\n+new\n*** End Patch"
    record: dict[str, object] = {
        "timestamp": "2026-06-11T00:00:00+00:00",
        "platform": "opencode",
        "event_name": "PreToolUse",
        "session_id": "session-1",
        "tool_name": "apply_patch",
        "candidate_paths": ["app.py"],
        "tool_input": {"patchText": patch_text, "ignored_nested": {"x": "y"}},
    }

    assert format_item(record) == {
        "timestamp": "2026-06-11T00:00:00+00:00",
        "platform": "opencode",
        "event_name": "PreToolUse",
        "session_id": "session-1",
        "tool_name": "apply_patch",
        "candidate_paths": ["app.py"],
        "languages": [],
        "model": None,
        "provider": None,
        "command": None,
        "tool_output": None,
        "tool_input": {"patchText": patch_text},
        "platform_source": "explicit",
    }


def test_format_item_result_preserves_apply_patch_tool_input() -> None:
    patch_text = "*** Begin Patch\n*** Update File: app.py\n-old\n+new\n*** End Patch"
    record: dict[str, object] = {
        "timestamp": "2026-06-11T00:00:00+00:00",
        "platform": "opencode",
        "event_name": "PostToolUse",
        "session_id": "session-1",
        "tool_name": "apply_patch",
        "findings": [],
        "errors": [],
        "tool_input": {"patchText": patch_text},
    }

    assert format_item(record) == {
        "timestamp": "2026-06-11T00:00:00+00:00",
        "platform": "opencode",
        "event_name": "PostToolUse",
        "session_id": "session-1",
        "tool_name": "apply_patch",
        "findings": [],
        "errors": [],
        "output": None,
        "skipped": False,
        "reason": None,
        "model": None,
        "provider": None,
        "command": None,
        "tool_output": None,
        "tool_input": {"patchText": patch_text},
        "platform_source": "explicit",
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


def test_format_item_event_preserves_lineage_metadata_aliases() -> None:
    record: dict[str, object] = {
        "timestamp": "2026-06-11T00:00:00+00:00",
        "platform": "cursor",
        "event_name": "PreToolUse",
        "session_id": "child-session",
        "parentSessionId": "parent-session",
        "rootSessionID": "root-session",
        "originPlatform": "claude",
        "originSessionID": "origin-session",
        "platformSource": "explicit",
        "subagentType": "explore",
        "spawnDescription": "Find lineage",
        "lineageRole": "child_mirror",
    }

    formatted = format_item(record)
    expected = {
        "platform": "cursor",
        "parent_session_id": "parent-session",
        "root_session_id": "root-session",
        "origin_platform": "claude",
        "origin_session_id": "origin-session",
        "platform_source": "explicit",
        "subagent_type": "explore",
        "spawn_description": "Find lineage",
        "lineage_role": "child_mirror",
    }

    assert formatted is not None, "event records should format for projection"
    assert {key: formatted.get(key) for key in expected} == expected


def test_format_item_event_normalizes_invalid_lineage_platform_metadata() -> None:
    record: dict[str, object] = {
        "timestamp": "2026-06-11T00:00:00+00:00",
        "platform": "cursor",
        "event_name": "PreToolUse",
        "session_id": "child-session",
        "originPlatform": "windsurf",
        "platformSource": "unexpected-source",
    }

    formatted = format_item(record)

    assert formatted is not None, "event records should format for projection"
    assert formatted["origin_platform"] == "unknown", (
        "unsupported lineage origin platforms should not leak into dashboard data"
    )
    assert formatted["platform_source"] == "explicit", (
        "invalid platform_source metadata should be replaced with derived provenance"
    )


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
        "tool_input": None,
    }

    assert format_item(record) == {
        "timestamp": "",
        "platform": "unknown",
        "event_name": "PostToolUse",
        "session_id": "session-1",
        "tool_name": "",
        "candidate_paths": [],
        "languages": [],
        "model": None,
        "provider": None,
        "command": command,
        "tool_output": tool_output,
        "tool_input": None,
        "platform_source": "unknown",
    }
