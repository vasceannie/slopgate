"""Runtime settings for the ForceDash canvas server."""

from pathlib import Path
import os

CANVAS_DIR = Path.home() / ".openclaw/canvas/forcedash"
SSH_HOST = os.environ.get("SLOPGATE_SSH_HOST", "little")
CONFIG_PATH = os.environ.get("SLOPGATE_CONFIG_PATH", "~/.config/slopgate/config.json")
TRACE_DIR = os.environ.get("SLOPGATE_TRACE_DIR", "~/.config/slopgate/logs")
PORT = int(os.environ.get("PORT", "18834"))
BIND = os.environ.get("BIND", "0.0.0.0")

CONNECT_TIMEOUT_SECONDS = 5
REMOTE_COMMAND_TIMEOUT_SECONDS = 8
SSE_HEARTBEAT_SECONDS = 15
SSE_SLEEP_SECONDS = 1
PROCESS_SHUTDOWN_TIMEOUT_SECONDS = 2
SNAPSHOT_TIMEOUT_SECONDS = 90
DEFAULT_LOOKBACK_HOURS = 168
MIN_LOOKBACK_HOURS = 1
MAX_LOOKBACK_HOURS = 720
HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_NOT_FOUND = 404
HTTP_METHOD_NOT_ALLOWED = 405
HTTP_BAD_GATEWAY = 502
