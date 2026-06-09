"""Server-sent event streaming from remote slopgate JSONL logs."""
import http.server
import subprocess
import time

from forcedash_server.config import (
    CONNECT_TIMEOUT_SECONDS,
    PROCESS_SHUTDOWN_TIMEOUT_SECONDS,
    SSE_HEARTBEAT_SECONDS,
    SSE_SLEEP_SECONDS,
    SSH_HOST,
)

REMOTE_TAIL_SCRIPT = (
    "from pathlib import Path\n"
    "import subprocess\n"
    "log_dir = Path.home() / '.config' / 'slopgate' / 'logs'\n"
    "files = [log_dir / 'events.jsonl', log_dir / 'rules.jsonl', log_dir / 'results.jsonl', "
    "log_dir / 'subprocess.jsonl', log_dir / 'async' / 'subprocess.jsonl']\n"
    "files = [p for p in files if p.exists()]\n"
    "cmd = ['stdbuf', '-oL', 'tail', '-n', '20', '-F', *map(str, files)]\n"
    "subprocess.run(cmd, check=False)\n"
)


def stream_tail(handler: http.server.SimpleHTTPRequestHandler) -> None:
    proc = open_tail_process()
    try:
        write_tail_events(handler, proc)
    except (BrokenPipeError, ConnectionResetError):
        return
    finally:
        stop_tail_process(proc)


def open_tail_process() -> subprocess.Popen[str]:
    return subprocess.Popen(
        [
            "ssh",
            "-o",
            f"ConnectTimeout={CONNECT_TIMEOUT_SECONDS}",
            SSH_HOST,
            f"python3 - <<'PY'\n{REMOTE_TAIL_SCRIPT}PY",
        ],
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        bufsize=1,
    )


def write_tail_events(
    handler: http.server.SimpleHTTPRequestHandler,
    proc: subprocess.Popen[str],
) -> None:
    if proc.stdout is None:
        return
    last_heartbeat = time.monotonic()
    while proc.poll() is None:
        last_heartbeat = write_next_line(handler, proc, last_heartbeat)


def write_next_line(
    handler: http.server.SimpleHTTPRequestHandler,
    proc: subprocess.Popen[str],
    last_heartbeat: float,
) -> float:
    if proc.stdout is None:
        return last_heartbeat
    line = proc.stdout.readline()
    if line:
        return write_data_line(handler, line, last_heartbeat)
    return maybe_write_heartbeat(handler, last_heartbeat)


def write_data_line(
    handler: http.server.SimpleHTTPRequestHandler,
    line: str,
    last_heartbeat: float,
) -> float:
    payload = line.strip()
    if not payload.startswith("{"):
        return last_heartbeat
    handler.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
    handler.wfile.flush()
    return time.monotonic()


def maybe_write_heartbeat(
    handler: http.server.SimpleHTTPRequestHandler,
    last_heartbeat: float,
) -> float:
    if time.monotonic() - last_heartbeat < SSE_HEARTBEAT_SECONDS:
        time.sleep(SSE_SLEEP_SECONDS)
        return last_heartbeat
    handler.wfile.write(b": keepalive\n\n")
    handler.wfile.flush()
    return time.monotonic()


def stop_tail_process(proc: subprocess.Popen[str]) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=PROCESS_SHUTDOWN_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=PROCESS_SHUTDOWN_TIMEOUT_SECONDS)
