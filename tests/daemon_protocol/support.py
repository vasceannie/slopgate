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


@dataclass(slots=True)
class DaemonResponseObservation:
    response: DaemonResponse
    server_alive: bool


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
