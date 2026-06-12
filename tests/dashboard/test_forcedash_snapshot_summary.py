from __future__ import annotations

import importlib
import json
import posixpath
import subprocess
import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "dashboard" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

_snapshot = importlib.import_module("forcedash_server.snapshot")
build_trace_snapshot_script = _snapshot.build_trace_snapshot_script

HOME_REPO_EVENT_PATH = posixpath.join(
    posixpath.sep, "home", "trav", "repos", "slopgate", "src", "a.py"
)


def test_trace_snapshot_script_labels_home_repo_paths_by_repo_name(
    tmp_path: Path,
) -> None:
    log_dir = tmp_path / ".config" / "slopgate" / "logs"
    log_dir.mkdir(parents=True)
    event = {
        "timestamp": "2026-06-12T00:00:00+00:00",
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
