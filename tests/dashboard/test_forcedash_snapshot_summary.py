from __future__ import annotations

import importlib
import json
import posixpath
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "dashboard" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

_snapshot = importlib.import_module("forcedash_server.snapshot")
build_trace_snapshot_script = _snapshot.build_trace_snapshot_script

HOME_REPO_EVENT_PATH = posixpath.join(
    posixpath.sep, "home", "trav", "repos", "slopgate", "src", "a.py"
)
APPLY_PATCH_TEXT = "*** Begin Patch\n*** Update File: app.py\n-old\n+new\n*** End Patch"
LINEAGE_ALIAS_FIELDS: dict[str, object] = {
    "parentSessionId": "parent-session",
    "rootSessionID": "root-session",
    "originPlatform": "claude",
    "originSessionID": "origin-session",
    "platformSource": "explicit",
    "subagentType": "explore",
    "spawnDescription": "Find lineage",
    "lineageRole": "child_mirror",
}
SESSION_TITLE_ALIAS_FIELDS: dict[str, object] = {
    "title": "Fix dashboard session labels",
}
RECENT_TRACE_TIMESTAMP = datetime.now(timezone.utc).isoformat()


def run_trace_snapshot_script(tmp_path: Path) -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, "-c", build_trace_snapshot_script(42)],
        check=True,
        capture_output=True,
        env={"HOME": str(tmp_path)},
        text=True,
    )
    payload = json.loads(result.stdout)
    assert isinstance(payload, dict), "Snapshot script should emit a JSON object"
    return payload


def base_event(**extra: object) -> dict[str, object]:
    event: dict[str, object] = {
        "timestamp": RECENT_TRACE_TIMESTAMP,
        "event_name": "PreToolUse",
        "session_id": "session-a",
        "tool_name": "Bash",
    }
    event.update(extra)
    return event


def write_event_log(tmp_path: Path, event: dict[str, object]) -> None:
    log_dir = tmp_path / ".config" / "slopgate" / "logs"
    log_dir.mkdir(parents=True)
    (log_dir / "events.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")


def projected_event(tmp_path: Path, event: dict[str, object]) -> dict[str, object]:
    write_event_log(tmp_path, event)
    data = run_trace_snapshot_script(tmp_path)["data"]
    assert isinstance(data, dict), "Snapshot payload should include projected data"
    typed_data: dict[str, object] = {str(key): value for key, value in data.items()}
    events = typed_data["events"]
    assert isinstance(events, list), "Snapshot data should include event records"
    first_event = events[0]
    assert isinstance(first_event, dict), "Projected event should be a JSON object"
    return {str(key): value for key, value in first_event.items()}


def test_trace_snapshot_script_labels_home_repo_paths_by_repo_name(
    tmp_path: Path,
) -> None:
    log_dir = tmp_path / ".config" / "slopgate" / "logs"
    log_dir.mkdir(parents=True)
    event = {
        "timestamp": RECENT_TRACE_TIMESTAMP,
        "platform": "codex",
        "event_name": "PreToolUse",
        "session_id": "session-a",
        "tool_name": "Bash",
        "candidate_paths": [HOME_REPO_EVENT_PATH],
    }
    (log_dir / "events.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-c", build_trace_snapshot_script(42)],
        check=True,
        capture_output=True,
        env={"HOME": str(tmp_path)},
        text=True,
    )
    summaries = json.loads(result.stdout)["summaries"]

    assert summaries["hottest_repos"] == [{"label": "slopgate", "count": 1}], (
        "Snapshot summaries should label /home/<user>/repos/<repo> paths by repo name"
    )


def test_trace_snapshot_script_preserves_apply_patch_tool_input(
    tmp_path: Path,
) -> None:
    log_dir = tmp_path / ".config" / "slopgate" / "logs"
    log_dir.mkdir(parents=True)
    event = {
        "timestamp": RECENT_TRACE_TIMESTAMP,
        "platform": "opencode",
        "event_name": "PreToolUse",
        "session_id": "session-a",
        "tool_name": "apply_patch",
        "candidate_paths": ["app.py"],
        "tool_input": {"patchText": APPLY_PATCH_TEXT},
    }
    (log_dir / "events.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "-c", build_trace_snapshot_script(42)],
        check=True,
        capture_output=True,
        env={"HOME": str(tmp_path)},
        text=True,
    )
    data = json.loads(result.stdout)["data"]

    assert data["events"][0]["tool_input"] == {"patchText": APPLY_PATCH_TEXT}, (
        "Snapshot projection should preserve apply_patch patchText for diff previews"
    )


def test_trace_snapshot_script_defaults_missing_platform_to_unknown(
    tmp_path: Path,
) -> None:
    event = base_event()

    projected = projected_event(tmp_path, event)

    assert projected["platform"] == "unknown", (
        "Remote snapshot projection should not default missing platforms to Claude"
    )
    assert projected["platform_source"] == "unknown", (
        "Remote snapshot projection should mark missing platform provenance as unknown"
    )


def test_trace_snapshot_script_preserves_cursor_platform(
    tmp_path: Path,
) -> None:
    event = base_event(platform="cursor")

    projected = projected_event(tmp_path, event)

    assert projected["platform"] == "cursor", (
        "Remote snapshot projection should preserve explicit Cursor platform values"
    )
    assert projected["platform_source"] == "explicit", (
        "Remote snapshot projection should mark known platform values as explicit"
    )


def test_trace_snapshot_script_normalizes_unsupported_platform_to_unknown(
    tmp_path: Path,
) -> None:
    event = base_event(platform="windsurf")

    projected = projected_event(tmp_path, event)

    assert projected["platform"] == "unknown", (
        "Remote snapshot projection should normalize unsupported platforms to unknown"
    )
    assert projected["platform_source"] == "normalized", (
        "Remote snapshot projection should mark unsupported platform provenance as normalized"
    )


def test_trace_snapshot_script_preserves_lineage_metadata_aliases(
    tmp_path: Path,
) -> None:
    event = base_event(
        platform="cursor",
        session_id="child-session",
        **LINEAGE_ALIAS_FIELDS,
    )

    projected = projected_event(tmp_path, event)
    expected = {
        "parent_session_id": "parent-session",
        "root_session_id": "root-session",
        "origin_platform": "claude",
        "origin_session_id": "origin-session",
        "platform_source": "explicit",
        "subagent_type": "explore",
        "spawn_description": "Find lineage",
        "lineage_role": "child_mirror",
    }

    assert {key: projected.get(key) for key in expected} == expected, (
        "Remote snapshot projection should canonicalize lineage aliases for grouped sessions"
    )


def test_trace_snapshot_script_preserves_session_title_aliases(
    tmp_path: Path,
) -> None:
    event = base_event(
        platform="opencode",
        sessionTitleSource="opencode-event",
        sessionIdentitySource="opencode-event",
        opencodeSessionId="ses_139981ae7ffeOKOMbswUJdo3Oy",
        secondarySessionIds=["opencode-plugin-synthetic"],
        **SESSION_TITLE_ALIAS_FIELDS,
    )

    projected = projected_event(tmp_path, event)

    assert projected["session_title"] == "Fix dashboard session labels", (
        "Remote snapshot projection should canonicalize explicit session title aliases"
    )
    assert projected["session_title_source"] == "opencode-event", (
        "Remote snapshot projection should preserve title provenance"
    )
    assert projected["session_identity_source"] == "opencode-event", (
        "Remote snapshot projection should preserve native identity provenance"
    )
    assert projected["opencode_session_id"] == "ses_139981ae7ffeOKOMbswUJdo3Oy", (
        "Remote snapshot projection should preserve native OpenCode ids"
    )
    assert projected["secondary_session_ids"] == ["opencode-plugin-synthetic"], (
        "Remote snapshot projection should preserve secondary identity ids"
    )


def test_trace_snapshot_script_preserves_codex_native_identity_aliases(
    tmp_path: Path,
) -> None:
    event = base_event(
        platform="codex",
        session_id="codex-hook-session",
        threadId="thr_native_codex",
        sessionIdentitySource="codex-thread",
    )

    projected = projected_event(tmp_path, event)

    assert projected["codex_session_id"] == "thr_native_codex", (
        "Remote snapshot projection should preserve native Codex thread ids"
    )
    assert projected["session_identity_source"] == "codex-thread", (
        "Remote snapshot projection should preserve Codex identity provenance"
    )


def test_trace_snapshot_script_normalizes_invalid_lineage_platform_metadata(
    tmp_path: Path,
) -> None:
    event = base_event(
        platform="cursor",
        originPlatform="windsurf",
        platformSource="unexpected-source",
    )

    projected = projected_event(tmp_path, event)

    assert projected["origin_platform"] == "unknown", (
        "Remote snapshot projection should normalize unsupported origin platforms"
    )
    assert projected["platform_source"] == "explicit", (
        "Remote snapshot projection should replace invalid platform_source metadata"
    )
