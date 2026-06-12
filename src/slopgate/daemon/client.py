"""Client helper for resident hook daemon calls."""

from __future__ import annotations

import json
from pathlib import Path
import socket

from slopgate.daemon.protocol import (
    DaemonRequest,
    DaemonResponse,
    decode_response,
    encode_request,
    read_frame,
    UNKNOWN_DAEMON_VALUE,
)
from slopgate.util import logger

DEFAULT_DAEMON_TIMEOUT_SECONDS = 1.0


def send_daemon_request(
    socket_path: Path,
    request: DaemonRequest,
    *,
    timeout: float = DEFAULT_DAEMON_TIMEOUT_SECONDS,
) -> DaemonResponse:
    logger.info(
        "hook daemon client request",
        socket_path=str(socket_path),
        platform=request.platform or UNKNOWN_DAEMON_VALUE,
        event=request.event or UNKNOWN_DAEMON_VALUE,
    )
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(timeout)
            client.connect(str(socket_path))
            client.sendall(encode_request(request))
            return decode_response(
                read_frame(
                    client,
                    empty_message="empty daemon response frame",
                    size_message="daemon response frame exceeds maximum size",
                )
            )
    except (
        json.JSONDecodeError,
        OSError,
        RuntimeError,
        UnicodeDecodeError,
        ValueError,
    ) as exc:
        logger.warning(
            "hook daemon client failed",
            socket_path=str(socket_path),
            error=exc.__class__.__name__,
        )
        return DaemonResponse(ok=False, error=str(exc))
