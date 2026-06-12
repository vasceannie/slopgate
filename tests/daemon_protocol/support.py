from __future__ import annotations

import importlib
import socket
import threading
import time
from collections.abc import Buffer, Callable
from dataclasses import asdict, dataclass
from pathlib import Path

_daemon_client = importlib.import_module("slopgate.daemon.client")
_daemon_protocol = importlib.import_module("slopgate.daemon.protocol")
_daemon_server = importlib.import_module("slopgate.daemon.server")

DaemonRequest = _daemon_protocol.DaemonRequest
DaemonResponse = _daemon_protocol.DaemonResponse
HookDaemonServer = _daemon_server.HookDaemonServer
send_daemon_request = _daemon_client.send_daemon_request
encode_request = _daemon_protocol.encode_request
decode_response = _daemon_protocol.decode_response

HAS_UNIX_SOCKETS = hasattr(socket, "AF_UNIX")
SOCKET_WAIT_TIMEOUT_SECONDS = 2.0
SOCKET_WAIT_INTERVAL_SECONDS = 0.01
SERVER_JOIN_TIMEOUT_SECONDS = 2.0
SOCKET_READ_BYTES = 4096
FAST_SERVER_CONNECTION_TIMEOUT_SECONDS = 0.05
CLIENT_READ_TIMEOUT_SECONDS = 1.0
REQUEST_START_TIMEOUT_SECONDS = 1.0
REQUEST_BLOCKED_OBSERVATION_SECONDS = 0.15


@dataclass(slots=True)
class DaemonResponseObservation:
    response: DaemonResponse
    server_alive: bool


@dataclass(frozen=True, slots=True)
class CoordinatedRequestObservation:
    first_started: bool
    second_started_while_first_blocked: bool
    second_started_after_release: bool
    first_response: DaemonResponse | None
    second_response: DaemonResponse | None
    server_alive: bool
    started_order: tuple[str, ...]


@dataclass(slots=True)
class _ObservedHookRequest:
    command: object
    platform: str | None
    event: str | None
    source: object


class EchoObservedHookRequest:
    def __call__(self, request: DaemonRequest) -> DaemonResponse:
        observed = _ObservedHookRequest(
            command=request.payload.get("command"),
            platform=request.platform,
            event=request.event,
            source=request.metadata.get("source"),
        )
        return DaemonResponse(ok=True, output=asdict(observed))


@dataclass(slots=True)
class RaisingHookRequestHandler:
    error: Exception

    def __call__(self, _request: DaemonRequest) -> DaemonResponse:
        raise self.error


class RejectingHookRequestHandler:
    def __call__(self, request: DaemonRequest) -> DaemonResponse:
        return DaemonResponse(
            ok=not bool(request.payload),
            stderr="blocked\n",
            exit_code=2,
        )


class UnserializableHookRequestHandler:
    def __call__(self, _request: DaemonRequest) -> DaemonResponse:
        return DaemonResponse(ok=True, output={"bad": object()})


class CoordinatedHookRequestHandler:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._started: dict[str, threading.Event] = {}
        self._release: dict[str, threading.Event] = {}
        self.started_order: list[str] = []

    def __call__(self, request: DaemonRequest) -> DaemonResponse:
        request_id = _request_id(request)
        with self._lock:
            self.started_order.append(request_id)
            self._started_event(request_id).set()
            release = self._release_event(request_id)
        _ = release.wait(SERVER_JOIN_TIMEOUT_SECONDS)
        return DaemonResponse(ok=True, output={"request_id": request_id})

    def wait_started(self, request_id: str, timeout: float) -> bool:
        return self._started_event(request_id).wait(timeout)

    def release(self, request_id: str) -> None:
        self._release_event(request_id).set()

    def release_all(self) -> None:
        with self._lock:
            release_events = list(self._release.values())
        for release in release_events:
            release.set()

    def _started_event(self, request_id: str) -> threading.Event:
        with self._lock:
            return self._started.setdefault(request_id, threading.Event())

    def _release_event(self, request_id: str) -> threading.Event:
        with self._lock:
            return self._release.setdefault(request_id, threading.Event())


class DaemonClientThread:
    def __init__(self, socket_path: Path, request: DaemonRequest) -> None:
        self._socket_path = socket_path
        self._request = request
        self.response: DaemonResponse | None = None
        self.thread = threading.Thread(target=self._send_request)

    def start(self) -> None:
        self.thread.start()

    def join(self) -> None:
        self.thread.join(timeout=SERVER_JOIN_TIMEOUT_SECONDS)

    def _send_request(self) -> None:
        self.response = send_daemon_request(self._socket_path, self._request)


def _request_id(request: DaemonRequest) -> str:
    raw_id = request.payload.get("request_id")
    return raw_id if isinstance(raw_id, str) else "unknown"


class DisconnectingResponseSocket(socket.socket):
    def __init__(self, request: DaemonRequest) -> None:
        super().__init__(socket.AF_UNIX, socket.SOCK_STREAM)
        self._frame = encode_request(request)
        self.response_frame = b""

    def recv(self, _size: int, _flags: int = 0, /) -> bytes:
        frame = self._frame
        self._frame = b""
        return frame

    def sendall(self, data: Buffer, flags: int = 0, /) -> None:
        self.response_frame = bytes(data)
        raise BrokenPipeError("client disconnected")


def wait_for_socket(socket_path: Path) -> None:
    deadline = time.monotonic() + SOCKET_WAIT_TIMEOUT_SECONDS
    waiter = threading.Event()
    while time.monotonic() < deadline:
        if socket_path.exists():
            return
        waiter.wait(SOCKET_WAIT_INTERVAL_SECONDS)
    raise AssertionError(f"socket was not created: {socket_path}")


def serve_one_request(
    socket_path: Path, response_handler: Callable[[DaemonRequest], DaemonResponse]
) -> threading.Thread:
    server = HookDaemonServer(socket_path, response_handler)
    thread = threading.Thread(target=server.serve, kwargs={"max_requests": 1})
    thread.start()
    wait_for_socket(socket_path)
    return thread


def serve_requests(
    socket_path: Path,
    response_handler: Callable[[DaemonRequest], DaemonResponse],
    *,
    max_requests: int,
) -> threading.Thread:
    server = HookDaemonServer(socket_path, response_handler)
    thread = threading.Thread(
        target=server.serve, kwargs={"max_requests": max_requests}
    )
    thread.start()
    wait_for_socket(socket_path)
    return thread


def observe_parallel_request_start(
    socket_path: Path,
    first_request: DaemonRequest,
    second_request: DaemonRequest,
) -> CoordinatedRequestObservation:
    handler = CoordinatedHookRequestHandler()
    server_thread = serve_requests(socket_path, handler, max_requests=2)
    first_client = DaemonClientThread(socket_path, first_request)
    second_client = DaemonClientThread(socket_path, second_request)

    first_client.start()
    first_started = handler.wait_started("first", REQUEST_START_TIMEOUT_SECONDS)
    second_client.start()
    second_started = handler.wait_started("second", REQUEST_BLOCKED_OBSERVATION_SECONDS)
    handler.release("first")
    handler.release("second")
    first_client.join()
    second_client.join()
    server_thread.join(timeout=SERVER_JOIN_TIMEOUT_SECONDS)
    return CoordinatedRequestObservation(
        first_started=first_started,
        second_started_while_first_blocked=second_started,
        second_started_after_release=second_started,
        first_response=first_client.response,
        second_response=second_client.response,
        server_alive=server_thread.is_alive(),
        started_order=tuple(handler.started_order),
    )


def observe_serialized_request_start(
    socket_path: Path,
    first_request: DaemonRequest,
    second_request: DaemonRequest,
) -> CoordinatedRequestObservation:
    handler = CoordinatedHookRequestHandler()
    server_thread = serve_requests(socket_path, handler, max_requests=2)
    first_client = DaemonClientThread(socket_path, first_request)
    second_client = DaemonClientThread(socket_path, second_request)

    first_client.start()
    first_started = handler.wait_started("first", REQUEST_START_TIMEOUT_SECONDS)
    second_client.start()
    second_started_while_blocked = handler.wait_started(
        "second", REQUEST_BLOCKED_OBSERVATION_SECONDS
    )
    handler.release("first")
    second_started_after_release = handler.wait_started(
        "second", REQUEST_START_TIMEOUT_SECONDS
    )
    handler.release("second")
    first_client.join()
    second_client.join()
    server_thread.join(timeout=SERVER_JOIN_TIMEOUT_SECONDS)
    return CoordinatedRequestObservation(
        first_started=first_started,
        second_started_while_first_blocked=second_started_while_blocked,
        second_started_after_release=second_started_after_release,
        first_response=first_client.response,
        second_response=second_client.response,
        server_alive=server_thread.is_alive(),
        started_order=tuple(handler.started_order),
    )


def observe_single_daemon_request(
    socket_path: Path,
    response_handler: Callable[[DaemonRequest], DaemonResponse],
    request: DaemonRequest,
) -> DaemonResponseObservation:
    thread = serve_one_request(socket_path, response_handler)
    response = send_daemon_request(socket_path, request)
    thread.join(timeout=SERVER_JOIN_TIMEOUT_SECONDS)
    return DaemonResponseObservation(response=response, server_alive=thread.is_alive())


def send_raw_daemon_frame(socket_path: Path, frame: bytes) -> bytes:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(str(socket_path))
        client.sendall(frame)
        return client.recv(SOCKET_READ_BYTES)


def serve_raw_daemon_response(
    socket_path: Path, response_frame: bytes
) -> threading.Thread:
    def serve_response() -> None:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server_socket:
            server_socket.bind(str(socket_path))
            server_socket.listen()
            connection, _ = server_socket.accept()
            with connection:
                _ = connection.recv(SOCKET_READ_BYTES)
                connection.sendall(response_frame)

    thread = threading.Thread(target=serve_response)
    thread.start()
    wait_for_socket(socket_path)
    return thread


def observe_idle_daemon_response(socket_path: Path) -> DaemonResponseObservation:
    server = HookDaemonServer(
        socket_path,
        EchoObservedHookRequest(),
        connection_timeout=FAST_SERVER_CONNECTION_TIMEOUT_SECONDS,
    )
    thread = threading.Thread(target=server.serve, kwargs={"max_requests": 1})
    thread.start()
    wait_for_socket(socket_path)

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(CLIENT_READ_TIMEOUT_SECONDS)
        client.connect(str(socket_path))
        raw_response = client.recv(SOCKET_READ_BYTES)

    thread.join(timeout=SERVER_JOIN_TIMEOUT_SECONDS)
    return DaemonResponseObservation(
        response=decode_response(raw_response),
        server_alive=thread.is_alive(),
    )
