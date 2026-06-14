"""Focused gates for Stop quality-reminder lifecycle behavior."""

from __future__ import annotations

from pathlib import Path

from slopgate.engine import evaluate_payload

from tests.support import assert_blocked, finding_ids, output_string, require_output


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


def _assert_opencode_context_reminder(bundle_root: Path, session_id: str) -> None:
    result = evaluate_payload(
        _opencode_idle_payload(bundle_root, session_id), platform="opencode"
    )
    output = require_output(result)
    assert output_string(output, "action") == "context"
    assert "slopgate lint check" in str(output)
    assert "STOP-002" in finding_ids(result)


def test_opencode_stop_quality_reminder_dedupes_same_session(bundle_root: Path) -> None:
    _assert_opencode_context_reminder(bundle_root, "opencode-stop-session")

    second_result = evaluate_payload(
        _opencode_idle_payload(bundle_root, "opencode-stop-session"),
        platform="opencode",
    )
    second_rule_ids = finding_ids(second_result)

    assert "STOP-002" not in second_rule_ids


def test_opencode_stop_quality_reminder_allows_new_session(bundle_root: Path) -> None:
    session_id = "opencode-stop-session-fresh"

    _assert_opencode_context_reminder(bundle_root, session_id)

    next_result = evaluate_payload(
        _opencode_idle_payload(bundle_root, f"{session_id}-next"),
        platform="opencode",
    )
    assert "STOP-002" in finding_ids(next_result)


def test_stop_quality_reminder_uses_configured_command(tmp_path: Path) -> None:
    _ = (tmp_path / "slopgate.toml").write_text(
        '[hook_guidance]\nquality_check_command = "uv run pytest -q"\n',
        encoding="utf-8",
    )

    result = evaluate_payload(
        _stop_payload(tmp_path, "configured-stop-session", "All tasks complete.")
    )

    output = require_output(result)
    assert "uv run pytest -q" in str(output)
    assert "STOP-002" in finding_ids(result)


def test_stop_quality_reminder_dedupe_preserves_blocking_stop_rules(
    bundle_root: Path,
) -> None:
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
