from __future__ import annotations

import importlib
import os
import sys
import json
import subprocess
from collections.abc import Callable
from http.server import SimpleHTTPRequestHandler
from io import BytesIO
from pathlib import Path
from typing import cast

import pytest
from hypothesis import given, strategies

SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "dashboard" / "scripts"
SRC_DIR = Path(__file__).resolve().parents[2] / "src"
sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(SRC_DIR))

_harness = importlib.import_module("forcedash_server.harness")
_snapshot = importlib.import_module("forcedash_server.snapshot")
streaming = importlib.import_module("forcedash_server.streaming")

parse_harness_payload = _harness.parse_harness_payload
build_trace_snapshot_script = _snapshot.build_trace_snapshot_script
parse_snapshot_payload = _snapshot.parse_snapshot_payload
snapshot_lookback_hours = _snapshot.snapshot_lookback_hours

PayloadParser = Callable[[str], tuple[dict[str, object], str | None]]
JSON_SCALAR_STRATEGY = strategies.one_of(
    strategies.none(),
    strategies.booleans(),
    strategies.integers(min_value=-1_000_000, max_value=1_000_000),
    strategies.text(max_size=40),
)
JSON_OBJECT_STRATEGY = strategies.dictionaries(
    strategies.text(min_size=1, max_size=16),
    JSON_SCALAR_STRATEGY,
    max_size=8,
)


class _StreamHandler:
    def __init__(self) -> None:
        self.wfile = BytesIO()


class _TailProcess:
    def __init__(self, stdout: object | None = None) -> None:
        self.stdout = stdout
        self.terminated: bool = False
        self.killed: bool = False
        self.wait_calls: int = 0
        self.poll_calls: int = 0

    def poll(self) -> int | None:
        self.poll_calls += 1
        return None if self.poll_calls == 1 else 0

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: int) -> int:
        del timeout
        self.wait_calls += 1
        return 0

    def kill(self) -> None:
        self.killed = True


class _TimeoutTailProcess(_TailProcess):
    def poll(self) -> int | None:
        return None

    def wait(self, timeout: int) -> int:
        wait_timeout = timeout
        self.wait_calls += 1
        raise subprocess.TimeoutExpired("ssh", wait_timeout)


class _LineReader:
    def __init__(self, lines: list[str]) -> None:
        self._lines = lines

    def readline(self) -> str:
        if not self._lines:
            return ""
        return self._lines.pop(0)


class _IdlePipeReader:
    def __init__(self) -> None:
        self._read_fd, self._write_fd = os.pipe()

    def fileno(self) -> int:
        return self._read_fd

    def readline(self) -> str:
        raise AssertionError("idle selectable stdout should not be read")

    def close(self) -> None:
        os.close(self._read_fd)
        os.close(self._write_fd)


def _write_next_line_from_reader(reader: _IdlePipeReader) -> tuple[bool, bytes]:
    handler = _StreamHandler()
    proc = _TailProcess(reader)
    try:
        wrote_line = streaming._write_next_line(
            cast(SimpleHTTPRequestHandler, handler), cast(subprocess.Popen[str], proc)
        )
        return wrote_line, handler.wfile.getvalue()
    finally:
        reader.close()


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/api/snapshot", 168),
        ("/api/snapshot?lookback_hours=2", 2),
        ("/api/snapshot?hours=9999", 720),
        ("/api/snapshot?hours=bad", 168),
        ("/api/snapshot?hours=0", 1),
    ],
)
def test_snapshot_lookback_hours_clamps_query_values(path: str, expected: int) -> None:
    assert snapshot_lookback_hours(path) == expected, (
        f"Expected {path} to resolve to {expected} hours"
    )


@pytest.mark.parametrize(
    ("parser", "error_text"),
    [
        (parse_harness_payload, "Harness status payload must be a JSON object"),
        (parse_snapshot_payload, "Snapshot payload must be a JSON object"),
    ],
)
def test_remote_payload_parsers_reject_non_object_json(
    parser: PayloadParser, error_text: str
) -> None:
    payload, error = parser("[]")

    assert payload == {}, "Expected invalid remote payload to return an empty object"
    assert error == error_text, "Expected parser-specific non-object error text"


@given(JSON_OBJECT_STRATEGY)
def test_parse_snapshot_payload_round_trips_json_objects(
    payload: dict[str, object],
) -> None:
    snapshot, error = parse_snapshot_payload(json.dumps(payload))

    assert snapshot == payload, (
        "Expected snapshot parser to preserve JSON object payloads"
    )
    assert error is None, "Expected valid JSON object payloads to parse without error"


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param("", id="empty"),
        pytest.param("{", id="truncated-object"),
        pytest.param('{"ok":', id="missing-value"),
    ],
)
def test_parse_snapshot_payload_rejects_malformed_json(payload: str) -> None:
    snapshot, error = parse_snapshot_payload(payload)

    assert snapshot == {}, "Expected malformed snapshot JSON to return an empty object"
    assert error is not None and error.startswith("Snapshot parse error:"), (
        "Expected malformed snapshot JSON to include parse error detail"
    )


def test_build_trace_snapshot_script_substitutes_runtime_tokens() -> None:
    script = build_trace_snapshot_script(42)

    assert "LOOKBACK_HOURS = 42" in script, "Expected lookback token to be replaced"
    assert "__LOOKBACK_HOURS__" not in script, "Expected no unresolved lookback token"
    assert "__SSH_HOST__" not in script, "Expected no unresolved SSH host token"


def test_trace_snapshot_script_emits_server_side_summaries(tmp_path: Path) -> None:
    script = build_trace_snapshot_script(42)
    result = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        env={"HOME": str(tmp_path)},
        text=True,
    )
    payload = json.loads(result.stdout)

    assert payload["summaries"] == {
        "session_count": 0,
        "decision_counts": {
            "allow": 0,
            "deny": 0,
            "block": 0,
            "ask": 0,
            "context": 0,
            "warn": 0,
            "info": 0,
        },
        "hottest_repos": [],
        "top_rules": [],
        "subprocess_failures": 0,
    }, "Expected snapshot script to publish compact dashboard summaries"


def test_streaming_data_line_uses_sse_data_frame() -> None:
    handler = _StreamHandler()

    streaming._write_data_line(
        cast(SimpleHTTPRequestHandler, handler), '{"event_name":"PreToolUse"}\n'
    )

    assert handler.wfile.getvalue() == b'data: {"event_name":"PreToolUse"}\n\n'


def test_streaming_idle_pipe_does_not_block_waiting_for_next_line() -> None:
    wrote_line, body = _write_next_line_from_reader(_IdlePipeReader())

    assert wrote_line is False, "Idle tail stdout should let heartbeat logic run"
    assert body == b"", "Idle tail stdout should not emit data"


def test_streaming_heartbeat_is_rate_limited(monkeypatch: pytest.MonkeyPatch) -> None:
    handler = _StreamHandler()
    sleeps: list[int] = []
    monkeypatch.setattr(streaming.time, "monotonic", lambda: 10.0)
    monkeypatch.setattr(streaming.time, "sleep", sleeps.append)

    unchanged = streaming._maybe_write_heartbeat(
        cast(SimpleHTTPRequestHandler, handler), 9.0
    )
    emitted = streaming._maybe_write_heartbeat(
        cast(SimpleHTTPRequestHandler, handler), -10.0
    )

    assert {
        "unchanged": unchanged,
        "emitted": emitted,
        "sleeps": sleeps,
        "body": handler.wfile.getvalue(),
    } == {
        "unchanged": 9.0,
        "emitted": 10.0,
        "sleeps": [streaming.SSE_SLEEP_SECONDS],
        "body": b": heartbeat\n\n",
    }


def test_stream_tail_writes_lines_and_stops_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler = _StreamHandler()
    proc = _TailProcess(_LineReader(['{"rule_id":"PY-LOG-002"}\n']))

    def fake_popen(*_args: object, **_kwargs: object) -> _TailProcess:
        return proc

    monkeypatch.setattr(streaming.subprocess, "Popen", fake_popen)

    streaming.stream_tail(cast(SimpleHTTPRequestHandler, handler))

    assert handler.wfile.getvalue() == b'data: {"rule_id":"PY-LOG-002"}\n\n'
    assert {
        "terminated": proc.terminated,
        "killed": proc.killed,
    } == {"terminated": False, "killed": False}


def test_stream_tail_kills_process_when_terminate_times_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handler = _StreamHandler()
    proc = _TimeoutTailProcess(None)

    def fake_popen(*_args: object, **_kwargs: object) -> _TimeoutTailProcess:
        return proc

    def skip_write_tail_events(
        _handler: SimpleHTTPRequestHandler, _proc: subprocess.Popen[str]
    ) -> None:
        return None

    monkeypatch.setattr(streaming.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(streaming, "_write_tail_events", skip_write_tail_events)

    streaming.stream_tail(cast(SimpleHTTPRequestHandler, handler))

    assert {
        "terminated": proc.terminated,
        "killed": proc.killed,
        "wait_calls": proc.wait_calls,
    } == {"terminated": True, "killed": True, "wait_calls": 1}
