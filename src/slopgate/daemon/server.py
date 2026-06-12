"""Unix-socket server for resident hook evaluation."""

from __future__ import annotations

from collections.abc import Callable
import json
from pathlib import Path
import socket
import stat

from slopgate.daemon.protocol import (
    DaemonRequest,
    DaemonResponse,
    decode_request,
    encode_response,
    read_frame,
)
from slopgate.util import logger

HookRequestHandler = Callable[[DaemonRequest], DaemonResponse]


class HookDaemonServer:
    def __init__(self, socket_path: Path, handler: HookRequestHandler) -> None:
        self.socket_path = socket_path
        self._handler = handler

    def serve(self, *, max_requests: int | None = None) -> None:
        logger.info("hook daemon start", socket_path=str(self.socket_path))
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        self._unlink_socket()
        handled = 0
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.bind(str(self.socket_path))
            server.listen()
            while max_requests is None or handled < max_requests:
                connection, _ = server.accept()
                with connection:
                    self._handle_connection(connection)
                handled += 1
        self._unlink_socket()
        logger.info(
            "hook daemon stop", socket_path=str(self.socket_path), handled=handled
        )

    def _handle_connection(self, connection: socket.socket) -> None:
        try:
            request = decode_request(
                read_frame(
                    connection,
                    empty_message="empty daemon request frame",
                    size_message="daemon request frame exceeds maximum size",
                )
            )
            logger.info(
                "hook daemon request",
                socket_path=str(self.socket_path),
                platform=request.platform or "unknown",
                event=request.event or "unknown",
            )
            response = self._handler(request)
        except (
            json.JSONDecodeError,
            OSError,
            RuntimeError,
            UnicodeDecodeError,
            ValueError,
        ) as exc:
            logger.warning(
                "hook daemon request failed",
                socket_path=str(self.socket_path),
                error=exc.__class__.__name__,
            )
            response = DaemonResponse(ok=False, error=str(exc))
        connection.sendall(encode_response(response))

    def _unlink_socket(self) -> None:
        try:
            mode = self.socket_path.lstat().st_mode
        except FileNotFoundError:
            return
        if not stat.S_ISSOCK(mode):
            raise FileExistsError(
                f"refusing to unlink non-socket daemon path: {self.socket_path}"
            )
        self.socket_path.unlink()
