from __future__ import annotations

import importlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "dashboard" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

_snapshot = importlib.import_module("forcedash_server.snapshot")
build_trace_snapshot_script = _snapshot.build_trace_snapshot_script

SNAPSHOT_LOOKBACK_HOURS = 42


def _run_trace_snapshot_script(home: Path) -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, "-c", build_trace_snapshot_script(SNAPSHOT_LOOKBACK_HOURS)],
        check=True,
        capture_output=True,
        env={"HOME": str(home)},
        text=True,
    )
    parsed: object = json.loads(result.stdout)
    assert isinstance(parsed, dict), "Expected snapshot script to return an object"
    return cast(dict[str, object], parsed)


def _write_opencode_ack_trace_events(home: Path) -> str:
    log_dir = home / ".config" / "slopgate" / "logs"
    log_dir.mkdir(parents=True)
    timestamp = datetime.now(timezone.utc).isoformat()
    records = [
        {
            "timestamp": timestamp,
            "platform": "opencode",
            "event_name": "SessionStatus",
            "session_id": "opencode-live-session",
        },
        {
            "timestamp": timestamp,
            "platform": "opencode",
            "event_name": "PostToolUse",
            "session_id": "manual-session",
        },
        {
            "timestamp": timestamp,
            "platform": "codex",
            "event_name": "PreToolUse",
            "session_id": "codex-session",
        },
    ]
    (log_dir / "events.jsonl").write_text(
        "\n".join(json.dumps(record) for record in records),
        encoding="utf-8",
    )
    return timestamp


def test_trace_snapshot_script_summarizes_platform_and_opencode_ack(
    tmp_path: Path,
) -> None:
    timestamp = _write_opencode_ack_trace_events(tmp_path)
    payload = _run_trace_snapshot_script(tmp_path)
    summaries = cast(dict[str, object], payload["summaries"])

    assert summaries["platform_counts"] == {
        "codex": 1,
        "opencode": 2,
    }, "Expected dashboard summary to support platform/time-window triage"
    assert summaries["opencode_trace_ack"] == {
        "event_count": 2,
        "session_count": 2,
        "prefixed_session_count": 1,
        "latest_event_at": timestamp,
    }, "Expected OpenCode acknowledgement summary to check platform and session prefix"
