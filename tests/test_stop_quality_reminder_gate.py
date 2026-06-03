"""Focused gates for Stop quality-reminder lifecycle behavior."""

from __future__ import annotations

from pathlib import Path

from vibeforcer.engine import evaluate_payload

from tests.support import assert_blocked, finding_ids, output_string, require_output


def _stop_payload(bundle_root: Path, session_id: str, response: str) -> dict[str, object]:
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


def _opencode_stop_ids(bundle_root: Path, session_id: str) -> set[str]:
    return finding_ids(evaluate_payload(_opencode_idle_payload(bundle_root, session_id), platform="opencode"))


def _assert_opencode_context_reminder(bundle_root: Path, session_id: str) -> None:
    result = evaluate_payload(_opencode_idle_payload(bundle_root, session_id), platform="opencode")
    assert output_string(require_output(result), "action") == "context"
    assert "STOP-002" in finding_ids(result)


def test_opencode_stop_quality_reminder_dedupes_same_session(bundle_root: Path) -> None:
    _assert_opencode_context_reminder(bundle_root, "opencode-stop-session")

    second_rule_ids = _opencode_stop_ids(bundle_root, "opencode-stop-session")

    assert "STOP-002" not in second_rule_ids


def test_opencode_stop_quality_reminder_allows_new_session(bundle_root: Path) -> None:
    session_id = "opencode-stop-session-fresh"

    _assert_opencode_context_reminder(bundle_root, session_id)

    assert "STOP-002" in _opencode_stop_ids(bundle_root, f"{session_id}-next")


def test_stop_quality_reminder_dedupe_preserves_blocking_stop_rules(bundle_root: Path) -> None:
    session_id = "stop-dedupe-block-session"
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

    assert "STOP-001" in finding_ids(result)
    assert_blocked(result, "STOP-001")
