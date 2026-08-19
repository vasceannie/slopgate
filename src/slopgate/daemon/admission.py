"""Non-blocking admission for overlapping resident-daemon hook requests."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import socket
import threading

from slopgate.daemon.protocol import DaemonResponse
from slopgate.util import logger

DAEMON_BUSY_ERROR = "daemon busy"


def try_acquire_admission(
    repo_lane: threading.Lock, worker_slots: threading.BoundedSemaphore
) -> bool:
    """Acquire repo and worker slots without waiting.

    Return True only when both locks are held. If the worker slot is unavailable
    after the repo lane succeeds, release the repo lane before returning False.
    """
    if not repo_lane.acquire(blocking=False):
        return False
    if worker_slots.acquire(blocking=False):
        return True
    repo_lane.release()
    return False


def refuse_busy_connection(
    connection: socket.socket,
    send_response: Callable[[socket.socket, DaemonResponse], None],
    socket_path: Path,
) -> None:
    """Reject an unadmitted connection so the client can fall back immediately."""
    logger.info(
        "hook daemon busy",
        socket_path=str(socket_path),
        error=DAEMON_BUSY_ERROR,
    )
    send_response(
        connection,
        DaemonResponse(ok=False, error=DAEMON_BUSY_ERROR, accepted=False),
    )
    connection.close()
