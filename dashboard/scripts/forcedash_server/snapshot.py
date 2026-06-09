"""Remote trace snapshot collection."""
import json
import subprocess
from urllib.parse import parse_qs, urlparse

from forcedash_server.config import (
    DEFAULT_LOOKBACK_HOURS,
    MAX_LOOKBACK_HOURS,
    MIN_LOOKBACK_HOURS,
    SNAPSHOT_TIMEOUT_SECONDS,
    SSH_HOST,
)
from forcedash_server.remote import run_remote_python
from forcedash_server.resources import read_remote_script
from forcedash_server.types import JSONDict, coerce_object_dict

TRACE_SNAPSHOT_SCRIPT = "trace_snapshot.py.txt"


def snapshot_lookback_hours(path: str) -> int:
    parsed = urlparse(path)
    params = parse_qs(parsed.query)
    raw = (params.get("lookback_hours") or params.get("hours") or [str(DEFAULT_LOOKBACK_HOURS)])[0]
    try:
        hours = int(raw)
    except (TypeError, ValueError):
        hours = DEFAULT_LOOKBACK_HOURS
    return max(MIN_LOOKBACK_HOURS, min(hours, MAX_LOOKBACK_HOURS))


def trace_snapshot(lookback_hours: int) -> tuple[JSONDict, str | None]:
    script = build_trace_snapshot_script(lookback_hours)
    try:
        result = run_remote_python(script, timeout=SNAPSHOT_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return {}, "SSH snapshot timeout"
    except OSError as exc:
        return {}, str(exc)
    if result.returncode != 0:
        return {}, f"SSH exited {result.returncode}: {result.stderr.strip()}"
    return parse_snapshot_payload(result.stdout)


def build_trace_snapshot_script(lookback_hours: int) -> str:
    script = read_remote_script(TRACE_SNAPSHOT_SCRIPT)
    return script.replace("__LOOKBACK_HOURS__", str(lookback_hours)).replace("__SSH_HOST__", SSH_HOST)


def parse_snapshot_payload(stdout: str) -> tuple[JSONDict, str | None]:
    try:
        payload: object = json.loads(stdout)
    except json.JSONDecodeError as exc:
        return {}, f"Snapshot parse error: {exc}"
    snapshot = coerce_object_dict(payload)
    if snapshot is None:
        return {}, "Snapshot payload must be a JSON object"
    return snapshot, None
