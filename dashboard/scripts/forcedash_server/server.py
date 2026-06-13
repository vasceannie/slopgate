"""HTTP server and API routing for ForceDash."""

from collections.abc import Mapping
import http.server
import json
import socket
from socketserver import BaseServer
import sys
from urllib.parse import urlparse

from slopgate.util import logger

from forcedash_server.config import (
    BIND,
    CANVAS_DIR,
    CONFIG_PATH,
    HTTP_BAD_GATEWAY,
    HTTP_BAD_REQUEST,
    HTTP_METHOD_NOT_ALLOWED,
    HTTP_NOT_FOUND,
    HTTP_OK,
    PORT,
    SSH_HOST,
)
from forcedash_server.config_api import (
    apply_config_patch,
    dashboard_config,
    read_config,
    write_config,
)
from forcedash_server.harness import harness_status
from forcedash_server.snapshot import snapshot_lookback_hours, trace_snapshot
from forcedash_server.streaming import stream_tail
from forcedash_server.types import coerce_object_dict


class ForceDashHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(
        self,
        request: socket.socket,
        client_address: tuple[str, int],
        server: BaseServer,
    ) -> None:
        super().__init__(request, client_address, server, directory=str(CANVAS_DIR))

    def log_message(self, format: str, *args: object) -> None:
        del format, args
        if "/api/" in self.path:
            print(f"[API] {self.command} {self.path}", file=sys.stderr, flush=True)

    def _cors(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self) -> None:
        self.send_response(HTTP_OK)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:
        if self.path.startswith("/api/"):
            self._handle_api_get()
            return
        super().do_GET()

    def do_POST(self) -> None:
        if self.path.startswith("/api/"):
            self._handle_api_post()
            return
        self.send_error(HTTP_METHOD_NOT_ALLOWED)

    def _handle_api_get(self) -> None:
        parsed_path = urlparse(self.path).path
        logger.info(
            "forcedash_api_request",
            method="GET",
            path=parsed_path,
            ssh_host=SSH_HOST,
            client_host=self.client_address[0],
        )
        route_get_request(self, parsed_path)

    def _handle_api_post(self) -> None:
        parsed_path = urlparse(self.path).path
        logger.info(
            "forcedash_api_request",
            method="POST",
            path=parsed_path,
            ssh_host=SSH_HOST,
            client_host=self.client_address[0],
        )
        route_post_request(self, parsed_path)

    def _json(self, data: Mapping[str, object], status: int = HTTP_OK) -> None:
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _stream_sse(self) -> None:
        try:
            self.send_response(HTTP_OK)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            self._cors()
            self.end_headers()
            self.wfile.write(b"retry: 3000\n\n")
            self.wfile.flush()
            stream_tail(self)
        except (BrokenPipeError, ConnectionResetError):
            return


def route_get_request(handler: ForceDashHandler, parsed_path: str) -> None:
    if parsed_path == "/api/config":
        send_config(handler)
        return
    if parsed_path == "/api/health":
        send_health(handler)
        return
    if parsed_path == "/api/harness/status":
        send_harness_status(handler)
        return
    if parsed_path == "/api/snapshot":
        send_snapshot(handler)
        return
    if parsed_path == "/api/stream":
        handler._stream_sse()
        return
    handler.send_error(HTTP_NOT_FOUND)


def route_post_request(handler: ForceDashHandler, parsed_path: str) -> None:
    if parsed_path != "/api/config":
        handler.send_error(HTTP_NOT_FOUND)
        return
    patch, err = read_patch_payload(handler)
    if err is not None:
        handler._json({"error": err}, HTTP_BAD_REQUEST)
        return
    update_config(handler, patch)


def send_config(handler: ForceDashHandler) -> None:
    config, err = read_config()
    if err is not None:
        handler._json({"error": err}, HTTP_BAD_GATEWAY)
        return
    handler._json(dashboard_config(config))


def send_health(handler: ForceDashHandler) -> None:
    _, err = read_config()
    handler._json(
        {"ok": True, "ssh_host": SSH_HOST, "ssh_ok": err is None, "ssh_error": err}
    )


def send_harness_status(handler: ForceDashHandler) -> None:
    status, err = harness_status()
    if err is not None:
        handler._json(
            {"ok": False, "ssh_host": SSH_HOST, "error": err}, HTTP_BAD_GATEWAY
        )
        return
    status["ssh_host"] = SSH_HOST
    handler._json(status)


def send_snapshot(handler: ForceDashHandler) -> None:
    snapshot, err = trace_snapshot(snapshot_lookback_hours(handler.path))
    if err is not None:
        handler._json(
            {"ok": False, "ssh_host": SSH_HOST, "error": err}, HTTP_BAD_GATEWAY
        )
        return
    handler._json(snapshot)


def read_patch_payload(
    handler: ForceDashHandler,
) -> tuple[dict[str, object], str | None]:
    try:
        length = int(handler.headers.get("Content-Length", 0))
        payload: object = json.loads(handler.rfile.read(length))
    except (json.JSONDecodeError, ValueError) as exc:
        return {}, f"Bad JSON: {exc}"
    patch = coerce_object_dict(payload)
    if patch is None:
        return {}, "Bad JSON: Config patch must be a JSON object"
    return patch, None


def update_config(handler: ForceDashHandler, patch: dict[str, object]) -> None:
    live, err = read_config()
    if err is not None:
        handler._json(
            {"error": f"Could not read config before write: {err}"}, HTTP_BAD_GATEWAY
        )
        return
    write_error = write_config(apply_config_patch(live, patch))
    if write_error is not None:
        handler._json({"error": write_error}, HTTP_BAD_GATEWAY)
        return
    handler._json({"ok": True})


def main() -> None:
    if not CANVAS_DIR.exists():
        print(f"Canvas dir not found: {CANVAS_DIR}", file=sys.stderr)
        sys.exit(1)
    server = http.server.ThreadingHTTPServer((BIND, PORT), ForceDashHandler)
    print(f"ForceDash  http://{BIND}:{PORT}/", file=sys.stderr, flush=True)
    print(
        f"Config API http://{BIND}:{PORT}/api/config  (SSH -> {SSH_HOST}:{CONFIG_PATH})",
        file=sys.stderr,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return
