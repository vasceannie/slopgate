"""Unix-socket server for resident hook evaluation."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from functools import partial
import json
from pathlib import Path
import socket
import stat
import threading
from typing import Protocol

from slopgate.daemon.protocol import (
    DaemonRequest,
    DaemonResponse,
    UNKNOWN_DAEMON_VALUE,
    decode_request,
    encode_response,
    read_frame,
)
from slopgate.daemon.scheduler import (
    DaemonRequestScheduler,
    DaemonServerOptions,
    RepoLockRegistry,
    repo_key_for_request,
)
from slopgate.util import logger

HookRequestHandler = Callable[[DaemonRequest], DaemonResponse]
DEFAULT_CONNECTION_TIMEOUT_SECONDS = 1.0
REQUEST_FAILURE_EXCEPTIONS = (
    KeyError,
    json.JSONDecodeError,
    OSError,
    RuntimeError,
    TypeError,
    UnicodeDecodeError,
    ValueError,
)


class _AcceptingSocket(Protocol):
    def accept(self) -> tuple[socket.socket, object]: ...


@dataclass(frozen=True, slots=True)
class AdmittedConnection:
    connection: socket.socket
    request: DaemonRequest
    repo_lane: threading.Lock
    worker_slots: threading.BoundedSemaphore


class HookDaemonServer:
    def __init__(
        self,
        socket_path: Path,
        handler: HookRequestHandler,
        *,
        connection_timeout: float = DEFAULT_CONNECTION_TIMEOUT_SECONDS,
        options: DaemonServerOptions | None = None,
    ) -> None:
        self.socket_path = socket_path
        self._connection_timeout = connection_timeout
        self._options = options or DaemonServerOptions()
        self._scheduler = DaemonRequestScheduler(socket_path, handler)
        self._repo_lanes = RepoLockRegistry()

    def serve(self, *, max_requests: int | None = None) -> None:
        logger.info(
            "hook daemon start",
            socket_path=str(self.socket_path),
            workers=self._options.worker_count,
            serial=self._options.serial,
        )
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        self._unlink_socket()
        handled = 0
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
                server.bind(str(self.socket_path))
                server.listen(self._options.worker_count)
                if self._options.serial:
                    handled = self._serve_serial(server, max_requests=max_requests)
                else:
                    handled = self._serve_concurrent(server, max_requests=max_requests)
        finally:
            self._unlink_socket()
            logger.info(
                "hook daemon stop", socket_path=str(self.socket_path), handled=handled
            )

    def _serve_serial(
        self, server: _AcceptingSocket, *, max_requests: int | None
    ) -> int:
        handled = 0
        while max_requests is None or handled < max_requests:
            connection, _ = server.accept()
            connection.settimeout(self._connection_timeout)
            with connection:
                self._handle_connection(connection)
            handled += 1
        return handled

    def _serve_concurrent(
        self, server: _AcceptingSocket, *, max_requests: int | None
    ) -> int:
        handled = 0
        futures: set[Future[None]] = set()
        worker_slots = threading.BoundedSemaphore(self._options.worker_count)
        with ThreadPoolExecutor(max_workers=self._options.worker_count) as executor:
            while max_requests is None or handled < max_requests:
                futures = _retain_pending_futures(futures)
                try:
                    connection, _ = server.accept()
                except OSError:
                    raise
                connection.settimeout(self._connection_timeout)
                try:
                    request = _read_request(self.socket_path, connection)
                except REQUEST_FAILURE_EXCEPTIONS as exc:
                    self._send_response(
                        connection, DaemonResponse(ok=False, error=str(exc))
                    )
                    connection.close()
                    handled += 1
                    continue
                repo_lane = self._repo_lanes.lock_for(repo_key_for_request(request))
                repo_lane.acquire()
                worker_slots.acquire()
                future = self._submit_connection(
                    executor,
                    AdmittedConnection(
                        connection=connection,
                        request=request,
                        repo_lane=repo_lane,
                        worker_slots=worker_slots,
                    ),
                )
                if future is not None:
                    futures.add(future)
                handled += 1
            _ = wait(futures)
        return handled

    def _submit_connection(
        self,
        executor: ThreadPoolExecutor,
        admitted: AdmittedConnection,
    ) -> Future[None] | None:
        try:
            future = executor.submit(
                self._handle_owned_request, admitted.connection, admitted.request
            )
        except RuntimeError as exc:
            _release_admission(admitted.repo_lane, admitted.worker_slots)
            self._send_response(
                admitted.connection, DaemonResponse(ok=False, error=str(exc))
            )
            admitted.connection.close()
            return None
        future.add_done_callback(
            partial(
                _finish_worker,
                self.socket_path,
                admitted.repo_lane,
                admitted.worker_slots,
            )
        )
        return future

    def _handle_owned_request(
        self, connection: socket.socket, request: DaemonRequest
    ) -> None:
        with connection:
            try:
                response = self._scheduler.evaluate(request)
            except REQUEST_FAILURE_EXCEPTIONS as exc:
                logger.warning(
                    "hook daemon request failed",
                    socket_path=str(self.socket_path),
                    error=exc.__class__.__name__,
                )
                response = DaemonResponse(ok=False, error=str(exc))
            self._send_response(connection, response)

    def _handle_connection(self, connection: socket.socket) -> None:
        try:
            response = self._scheduler.evaluate(
                _read_request(self.socket_path, connection)
            )
        except REQUEST_FAILURE_EXCEPTIONS as exc:
            logger.warning(
                "hook daemon request failed",
                socket_path=str(self.socket_path),
                error=exc.__class__.__name__,
            )
            response = DaemonResponse(ok=False, error=str(exc))
        self._send_response(connection, response)

    def _send_response(
        self, connection: socket.socket, response: DaemonResponse
    ) -> None:
        frame = self._encode_response(response)
        try:
            connection.sendall(frame)
        except OSError as exc:
            logger.warning(
                "hook daemon response dropped",
                socket_path=str(self.socket_path),
                error=exc.__class__.__name__,
                response_ok=response.ok,
            )

    def _encode_response(self, response: DaemonResponse) -> bytes:
        try:
            return encode_response(response)
        except (TypeError, ValueError) as exc:
            logger.warning(
                "hook daemon response encode failed",
                socket_path=str(self.socket_path),
                error=exc.__class__.__name__,
                response_ok=response.ok,
            )
            return encode_response(
                DaemonResponse(ok=False, error="daemon response serialization failed")
            )

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


def _retain_pending_futures(futures: set[Future[None]]) -> set[Future[None]]:
    return {future for future in futures if not future.done()}


def _read_request(socket_path: Path, connection: socket.socket) -> DaemonRequest:
    request = decode_request(
        read_frame(
            connection,
            empty_message="empty daemon request frame",
            size_message="daemon request frame exceeds maximum size",
        )
    )
    logger.info(
        "hook daemon request",
        socket_path=str(socket_path),
        platform=request.platform or UNKNOWN_DAEMON_VALUE,
        event=request.event or UNKNOWN_DAEMON_VALUE,
    )
    return request


def _finish_worker(
    socket_path: Path,
    repo_lane: threading.Lock,
    worker_slots: threading.BoundedSemaphore,
    future: Future[None],
) -> None:
    try:
        _log_worker_failure(socket_path, future)
    finally:
        _release_admission(repo_lane, worker_slots)


def _release_admission(
    repo_lane: threading.Lock, worker_slots: threading.BoundedSemaphore
) -> None:
    repo_lane.release()
    worker_slots.release()


def _log_worker_failure(socket_path: Path, future: Future[None]) -> None:
    try:
        exc = future.exception()
    except CancelledError:
        logger.warning("hook daemon worker cancelled", socket_path=str(socket_path))
        return
    if exc is not None:
        logger.warning(
            "hook daemon worker failed",
            socket_path=str(socket_path),
            error=exc.__class__.__name__,
        )
