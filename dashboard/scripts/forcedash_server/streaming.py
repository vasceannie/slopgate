"""Server-sent event streaming from remote slopgate JSONL logs."""

from __future__ import annotations

import http.server
import select
import subprocess
import time

from forcedash_server.config import (
    PROCESS_SHUTDOWN_TIMEOUT_SECONDS,
    REMOTE_COMMAND_TIMEOUT_SECONDS,
    SSE_HEARTBEAT_SECONDS,
    SSE_SLEEP_SECONDS,
    SSH_HOST,
    TRACE_DIR,
)

TAIL_SCRIPT = (
    "python3 - <<'PY'\n"
    "import pathlib, time\n"
    f"log_dir = pathlib.Path({TRACE_DIR!r}).expanduser()\n"
    "files = [log_dir / 'events.jsonl', log_dir / 'rules.jsonl', log_dir / 'results.jsonl', "
    "log_dir / 'subprocess.jsonl', log_dir / 'async' / 'subprocess.jsonl']\n"
    "positions = {path: path.stat().st_size if path.exists() else 0 for path in files}\n"
    "while True:\n"
    "    for path in files:\n"
    "        if not path.exists():\n"
    "            continue\n"
    "        with path.open('r', encoding='utf-8', errors='replace') as handle:\n"
    "            handle.seek(positions.get(path, 0))\n"
    "            for line in handle:\n"
    "                print(line.rstrip('\\n'), flush=True)\n"
    "            positions[path] = handle.tell()\n"
    "    time.sleep(0.5)\n"
    "PY"
)


def stream_tail(handler: http.server.SimpleHTTPRequestHandler) -> None:
    proc = subprocess.Popen(
        [
            "ssh",
            "-o",
            f"ConnectTimeout={REMOTE_COMMAND_TIMEOUT_SECONDS}",
            SSH_HOST,
            TAIL_SCRIPT,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        bufsize=1,
    )
    try:
        _write_tail_events(handler, proc)
    finally:
        _stop_tail_process(proc)


def _write_tail_events(
    handler: http.server.SimpleHTTPRequestHandler,
    proc: subprocess.Popen[str],
) -> None:
    last_heartbeat = time.monotonic()
    while proc.poll() is None:
        if _write_next_line(handler, proc):
            last_heartbeat = time.monotonic()
            continue
        last_heartbeat = _maybe_write_heartbeat(handler, last_heartbeat)


def _write_next_line(
    handler: http.server.SimpleHTTPRequestHandler,
    proc: subprocess.Popen[str],
) -> bool:
    if proc.stdout is None:
        return False
    if not _stream_has_line(proc.stdout):
        return False
    line = proc.stdout.readline()
    if not line:
        return False
    _write_data_line(handler, line)
    return True


def _stream_has_line(stdout: object) -> bool:
    fileno = getattr(stdout, "fileno", None)
    if not callable(fileno):
        return True
    try:
        ready, _unused_write, _unused_error = select.select([stdout], [], [], 0)
    except (OSError, ValueError):
        return True
    return bool(ready)


def _write_data_line(handler: http.server.SimpleHTTPRequestHandler, line: str) -> None:
    payload = line.strip()
    if not payload:
        return
    handler.wfile.write(f"data: {payload}\n\n".encode())
    handler.wfile.flush()


def _maybe_write_heartbeat(
    handler: http.server.SimpleHTTPRequestHandler, last_heartbeat: float
) -> float:
    now = time.monotonic()
    if now - last_heartbeat < SSE_HEARTBEAT_SECONDS:
        time.sleep(SSE_SLEEP_SECONDS)
        return last_heartbeat
    handler.wfile.write(b": heartbeat\n\n")
    handler.wfile.flush()
    return now


def _stop_tail_process(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=PROCESS_SHUTDOWN_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        proc.kill()
