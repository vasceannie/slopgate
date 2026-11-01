"""Focused gates for Stop quality-reminder lifecycle behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

from slopgate.engine import evaluate_payload

from tests.support import assert_blocked, finding_ids, output_string, require_output

MUTATING_TOOL_INPUTS: dict[str, dict[str, object]] = {
    "Write": {"file_path": "src/example.py", "content": "value = 1\n"},
    "Edit": {
        "file_path": "src/example.py",
        "old_string": "value = 1",
        "new_string": "value = 2",
    },
    "MultiEdit": {
        "file_path": "src/example.py",
        "edits": [{"old_string": "value = 1", "new_string": "value = 2"}],
    },
    "Bash": {"command": "printf 'value = 1\\n' > src/example.py"},
}

READ_ONLY_TOOL_INPUTS: dict[str, dict[str, object]] = {
    "Read": {"file_path": "src/example.py"},
    "Grep": {"pattern": "value"},
    "Glob": {"pattern": "*.py"},
}


def _stop_payload(
    bundle_root: Path, session_id: str, response: str
) -> dict[str, object]:
    return {
        "session_id": session_id,
        "cwd": str(bundle_root),
        "hook_event_name": "Stop",
        "stop_response": response,
    }


def _opencode_idle_payload(bundle_root: Path, session_id: str) -> dict[str, object]:
    return {
        "session_id": session_id,
        "cwd": str(bundle_root),
        "hook_event_name": "session.idle",
        "stop_response": "All tasks completed successfully.",
    }


def _post_tool_payload(
    bundle_root: Path,
    session_id: str,
    tool_name: str,
    tool_input: dict[str, object],
) -> dict[str, object]:
    return {
        "session_id": session_id,
        "cwd": str(bundle_root),
        "hook_event_name": "PostToolUse",
        "tool_name": tool_name,
        "tool_input": tool_input,
    }


def _record_tool_use(
    bundle_root: Path,
    session_id: str,
    tool_name: str,
    tool_input: dict[str, object],
) -> None:
    _ = evaluate_payload(
        _post_tool_payload(bundle_root, session_id, tool_name, tool_input)
    )


def _stop_rule_ids_after_tool_use(
    bundle_root: Path,
    session_prefix: str,
    tool_name: str,
    tool_input: dict[str, object],
) -> set[str]:
    session_id = f"{session_prefix}-{tool_name.lower()}"
    _record_tool_use(bundle_root, session_id, tool_name, tool_input)
    result = evaluate_payload(
        _stop_payload(bundle_root, session_id, "All tasks complete.")
    )
    return finding_ids(result)


def _assert_opencode_context_reminder(bundle_root: Path, session_id: str) -> None:
    _record_tool_use(bundle_root, session_id, "Write", MUTATING_TOOL_INPUTS["Write"])
    result = evaluate_payload(
        _opencode_idle_payload(bundle_root, session_id), platform="opencode"
    )
    output = require_output(result)
    assert output_string(output, "action") == "context", (
        f"expected context action for {session_id}, got {output}"
    )
    assert "slopgate lint check" in str(output), (
        f"expected lint check guidance for {session_id}, got {output}"
    )
    assert "STOP-002" in finding_ids(result), (
        f"expected STOP-002 for {session_id}, got {finding_ids(result)}"
    )


def test_opencode_stop_quality_reminder_dedupes_same_session(bundle_root: Path) -> None:
    _assert_opencode_context_reminder(bundle_root, "opencode-stop-session")

    second_result = evaluate_payload(
        _opencode_idle_payload(bundle_root, "opencode-stop-session"),
        platform="opencode",
    )
    second_rule_ids = finding_ids(second_result)

    assert "STOP-002" not in second_rule_ids, (
        f"expected second stop to be deduped, got {second_rule_ids}"
    )


def test_opencode_stop_quality_reminder_allows_new_session(bundle_root: Path) -> None:
    session_id = "opencode-stop-session-fresh"

    _assert_opencode_context_reminder(bundle_root, session_id)

    _record_tool_use(
        bundle_root, f"{session_id}-next", "Write", MUTATING_TOOL_INPUTS["Write"]
    )
    next_result = evaluate_payload(
        _opencode_idle_payload(bundle_root, f"{session_id}-next"),
        platform="opencode",
    )
    assert "STOP-002" in finding_ids(next_result), (
        "expected a fresh mutated session to receive the reminder, got "
        f"{finding_ids(next_result)}"
    )


@pytest.mark.parametrize(
    ("tool_name", "tool_input"),
    list(MUTATING_TOOL_INPUTS.items()),
    ids=list(MUTATING_TOOL_INPUTS),
)
def test_stop_quality_reminder_requires_code_change(
    bundle_root: Path,
    tool_name: str,
    tool_input: dict[str, object],
) -> None:
    rule_ids = _stop_rule_ids_after_tool_use(
        bundle_root, "stop-mutation", tool_name, tool_input
    )

    assert "STOP-002" in rule_ids, (
        f"expected mutation via {tool_name} to enable the reminder, got {rule_ids}"
    )


@pytest.mark.parametrize(
    ("tool_name", "tool_input"),
    list(READ_ONLY_TOOL_INPUTS.items()),
    ids=list(READ_ONLY_TOOL_INPUTS),
)
def test_stop_quality_reminder_skips_read_only_sessions(
    bundle_root: Path,
    tool_name: str,
    tool_input: dict[str, object],
) -> None:
    rule_ids = _stop_rule_ids_after_tool_use(
        bundle_root, "stop-read-only", tool_name, tool_input
    )

    assert "STOP-002" not in rule_ids, (
        f"expected read-only {tool_name} to suppress the reminder, got {rule_ids}"
    )


def test_stop_quality_reminder_skips_session_without_tool_use(
    bundle_root: Path,
) -> None:
    result = evaluate_payload(
        _stop_payload(bundle_root, "stop-read-only-chat", "Here is the answer.")
    )

    assert "STOP-002" not in finding_ids(result), (
        f"expected a conversation-only session to suppress the reminder, got "
        f"{finding_ids(result)}"
    )


def test_stop_quality_reminder_skips_failed_tool_use(bundle_root: Path) -> None:
    session_id = "stop-failed-write"
    payload = _post_tool_payload(
        bundle_root, session_id, "Write", MUTATING_TOOL_INPUTS["Write"]
    )
    payload["hook_event_name"] = "PostToolUseFailure"
    _ = evaluate_payload(payload)

    result = evaluate_payload(
        _stop_payload(bundle_root, session_id, "The edit failed and was not applied.")
    )

    assert "STOP-002" not in finding_ids(result), (
        f"expected a failed write to suppress the reminder, got {finding_ids(result)}"
    )


def test_stop_quality_reminder_uses_configured_command(tmp_path: Path) -> None:
    _ = (tmp_path / "slopgate.toml").write_text(
        '[hook_guidance]\nquality_check_command = "uv run pytest -q"\n',
        encoding="utf-8",
    )
    session_id = "configured-stop-session"
    _record_tool_use(tmp_path, session_id, "Write", MUTATING_TOOL_INPUTS["Write"])

    result = evaluate_payload(
        _stop_payload(tmp_path, session_id, "All tasks complete.")
    )

    output = require_output(result)
    assert "uv run pytest -q" in str(output), (
        f"expected configured command in reminder, got {output}"
    )
    assert "slopgate lint test-integrity" in str(output), (
        f"expected deferred test-integrity guidance in reminder, got {output}"
    )
    assert "STOP-002" in finding_ids(result), (
        f"expected STOP-002 after a code change, got {finding_ids(result)}"
    )


def test_stop_quality_reminder_dedupe_preserves_blocking_stop_rules(
    bundle_root: Path,
) -> None:
    session_id = "stop-dedupe-block-session"
    _record_tool_use(bundle_root, session_id, "Write", MUTATING_TOOL_INPUTS["Write"])
    _ = evaluate_payload(
        _stop_payload(bundle_root, session_id, "All tasks completed successfully.")
    )

    result = evaluate_payload(
        _stop_payload(
            bundle_root,
            session_id,
            "The type error was already existed before my changes.",
        )
    )

    assert "STOP-001" in finding_ids(result), (
        f"expected STOP-001 to still block, got {finding_ids(result)}"
    )
    assert_blocked(result, "STOP-001")


def test_subagent_stop_leaves_parent_stop_reminder(bundle_root: Path) -> None:
    session_id = "stop-subagent-shared-session"
    _record_tool_use(bundle_root, session_id, "Write", MUTATING_TOOL_INPUTS["Write"])
    subagent_payload = _stop_payload(bundle_root, session_id, "Subagent edit done.")
    subagent_payload["hook_event_name"] = "SubagentStop"
    _ = evaluate_payload(subagent_payload)

    parent = evaluate_payload(
        _stop_payload(bundle_root, session_id, "All tasks complete.")
    )

    assert "STOP-002" in finding_ids(parent), (
        f"expected the parent Stop to keep its reminder, got {finding_ids(parent)}"
    )


def _subagent_stop_ids(bundle_root: Path, session_id: str, response: str) -> set[str]:
    payload = _stop_payload(bundle_root, session_id, response)
    payload["hook_event_name"] = "SubagentStop"
    return finding_ids(evaluate_payload(payload))


def test_subagent_stop_reminder_dedupes_per_scope(bundle_root: Path) -> None:
    session_id = "stop-subagent-dedupe-session"
    _record_tool_use(bundle_root, session_id, "Write", MUTATING_TOOL_INPUTS["Write"])

    first = _subagent_stop_ids(bundle_root, session_id, "First subagent done.")
    second = _subagent_stop_ids(bundle_root, session_id, "Second subagent done.")
    parent = evaluate_payload(
        _stop_payload(bundle_root, session_id, "All tasks complete.")
    )

    assert "STOP-002" in first, f"first subagent stop should remind, got {first}"
    assert "STOP-002" not in second, (
        f"subagent reminders must dedupe within the parent session, got {second}"
    )
    assert "STOP-002" in finding_ids(parent), (
        "subagent reminders must not spend the parent Stop reminder, got "
        f"{finding_ids(parent)}"
    )


DISMISSAL_RESPONSES: dict[str, tuple[str, bool]] = {
    "prose-dismissal": (
        "These type errors already existed before my change.",
        True,
    ),
    "identifier-in-code-span": (
        "Flagged for follow-up: `PREEXISTING_PHRASES` matches raw substrings.",
        False,
    ),
    "quoted-hook-output-in-fence": (
        "Hook output:\n```\nDo not dismiss issues as pre-existing.\n```\nFixed.",
        False,
    ),
    "inline-code-citation": (
        "The rule flags `pre-existing` when it appears in prose.",
        False,
    ),
    "bare-identifier": ("Renamed the preexisting_phrases tuple.", False),
}


@pytest.mark.parametrize(
    ("response", "blocked"),
    list(DISMISSAL_RESPONSES.values()),
    ids=list(DISMISSAL_RESPONSES),
)
def test_stop_dismissal_check_ignores_code_and_identifiers(
    bundle_root: Path, response: str, blocked: bool
) -> None:
    payload = _stop_payload(bundle_root, "stop-dismissal-session", response)

    rule_ids = finding_ids(evaluate_payload(payload))

    assert ("STOP-001" in rule_ids) is blocked, (
        f"expected blocked={blocked} for {response!r}, got {rule_ids}"
    )
