from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
import socket
import threading

import pytest

from slopgate.daemon.protocol import decode_response
from slopgate.daemon.scheduler import DaemonServerOptions
from slopgate.daemon.server import AdmittedConnection
from tests.daemon_protocol.support import (
    CoordinatedHookRequestHandler,
    HookDaemonServer,
    REQUEST_BLOCKED_OBSERVATION_SECONDS,
    REQUEST_START_TIMEOUT_SECONDS,
    SOCKET_READ_BYTES,
    SERVER_JOIN_TIMEOUT_SECONDS,
    DaemonRequest,
    encode_request,
)

SINGLE_WORKER_COUNT = 1
MAX_PROBED_REQUESTS = 2
SUBMIT_FAILURE_MESSAGE = "cannot schedule new futures after shutdown"
HAS_SOCKETPAIR = hasattr(socket, "socketpair")

pytestmark = pytest.mark.skipif(
    not HAS_SOCKETPAIR, reason="backpressure tests use in-process socket pairs"
)


@dataclass(frozen=True, slots=True)
class AcceptBackpressureObservation:
    first_accepted: bool
    first_started: bool
    second_accepted_while_blocked: bool
    second_started_while_blocked: bool
    second_accepted_after_release: bool
    second_started_after_release: bool
    server_alive: bool


@dataclass(frozen=True, slots=True)
class SubmitFailureObservation:
    future_created: bool
    response_ok: bool
    response_error: str | None
    repo_lane_released: bool
    worker_slot_released: bool


class AcceptProbeServer:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._accepted = 0
        self._client_sockets: list[socket.socket] = []
        self.first_accepted = threading.Event()
        self.second_accepted = threading.Event()

    def accept(self) -> tuple[socket.socket, object]:
        request_id = self._next_request_id()
        server_socket, client_socket = socket.socketpair()
        client_socket.sendall(
            encode_request(DaemonRequest(payload={"request_id": request_id}))
        )
        self._client_sockets.append(client_socket)
        self._accepted_event(request_id).set()
        return server_socket, None

    def close_clients(self) -> None:
        for client_socket in self._client_sockets:
            client_socket.close()

    def _next_request_id(self) -> str:
        with self._lock:
            self._accepted += 1
            return "first" if self._accepted == 1 else "second"

    def _accepted_event(self, request_id: str) -> threading.Event:
        return self.first_accepted if request_id == "first" else self.second_accepted


def test_concurrent_daemon_does_not_accept_past_available_worker_slots(
    tmp_path: Path,
) -> None:
    observation = _observe_accept_backpressure(tmp_path / "slopgate.sock")

    assert observation.first_accepted, (
        "First request should be accepted into the only worker slot"
    )
    assert observation.first_started, (
        "First request should start before worker saturation is tested"
    )
    assert observation.second_accepted_while_blocked, (
        "Concurrent daemon may accept one same-lane request before repo admission"
    )
    assert not observation.second_started_while_blocked, (
        "Same-repo request should not start while the repo lane is occupied"
    )
    assert observation.second_accepted_after_release, (
        "Concurrent daemon should accept the next request after a worker slot is released"
    )
    assert observation.second_started_after_release, (
        "Second request should run after the first worker slot is released"
    )
    assert not observation.server_alive, (
        "Backpressured concurrent daemon should stop after max_requests are handled"
    )


def test_submit_failure_returns_error_and_releases_admission_locks(
    tmp_path: Path,
) -> None:
    observation = _observe_submit_failure(tmp_path / "slopgate.sock")

    assert not observation.future_created, (
        "Submit failure should not create a worker future"
    )
    assert observation.response_ok is False, (
        "Submit failure should return an error response"
    )
    assert observation.response_error == SUBMIT_FAILURE_MESSAGE, (
        "Submit failure should preserve the runtime failure reason"
    )
    assert observation.repo_lane_released, (
        "Submit failure should release the repo admission lane"
    )
    assert observation.worker_slot_released, (
        "Submit failure should release the worker admission slot"
    )


def _observe_submit_failure(socket_path: Path) -> SubmitFailureObservation:
    server_socket, client_socket = socket.socketpair()
    with server_socket, client_socket:
        server = HookDaemonServer(socket_path, CoordinatedHookRequestHandler())
        repo_lane = threading.Lock()
        worker_slots = threading.BoundedSemaphore(SINGLE_WORKER_COUNT)
        repo_lane.acquire()
        worker_slots.acquire()
        executor = ThreadPoolExecutor(max_workers=SINGLE_WORKER_COUNT)
        executor.shutdown()

        future = server._submit_connection(
            executor,
            AdmittedConnection(
                connection=server_socket,
                request=DaemonRequest(payload={"request_id": "first"}),
                repo_lane=repo_lane,
                worker_slots=worker_slots,
            ),
        )
        response = decode_response(client_socket.recv(SOCKET_READ_BYTES))
        repo_lane_released = repo_lane.acquire(blocking=False)
        worker_slot_released = worker_slots.acquire(blocking=False)
    return SubmitFailureObservation(
        future_created=future is not None,
        response_ok=response.ok,
        response_error=response.error,
        repo_lane_released=repo_lane_released,
        worker_slot_released=worker_slot_released,
    )


def _observe_accept_backpressure(socket_path: Path) -> AcceptBackpressureObservation:
    handler = CoordinatedHookRequestHandler()
    accept_probe = AcceptProbeServer()
    server = HookDaemonServer(
        socket_path,
        handler,
        options=DaemonServerOptions(workers=SINGLE_WORKER_COUNT),
    )
    server_thread = threading.Thread(
        target=server._serve_concurrent,
        args=(accept_probe,),
        kwargs={"max_requests": MAX_PROBED_REQUESTS},
    )

    server_thread.start()
    first_accepted = accept_probe.first_accepted.wait(REQUEST_START_TIMEOUT_SECONDS)
    first_started = handler.wait_started("first", REQUEST_START_TIMEOUT_SECONDS)
    second_accepted_while_blocked = accept_probe.second_accepted.wait(
        REQUEST_BLOCKED_OBSERVATION_SECONDS
    )
    second_started_while_blocked = handler.wait_started(
        "second", REQUEST_BLOCKED_OBSERVATION_SECONDS
    )
    handler.release("first")
    second_accepted_after_release = accept_probe.second_accepted.wait(
        REQUEST_START_TIMEOUT_SECONDS
    )
    second_started_after_release = handler.wait_started(
        "second", REQUEST_START_TIMEOUT_SECONDS
    )
    handler.release("second")
    server_thread.join(timeout=SERVER_JOIN_TIMEOUT_SECONDS)
    accept_probe.close_clients()
    return AcceptBackpressureObservation(
        first_accepted=first_accepted,
        first_started=first_started,
        second_accepted_while_blocked=second_accepted_while_blocked,
        second_started_while_blocked=second_started_while_blocked,
        second_accepted_after_release=second_accepted_after_release,
        second_started_after_release=second_started_after_release,
        server_alive=server_thread.is_alive(),
    )
