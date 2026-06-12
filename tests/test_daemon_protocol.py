from __future__ import annotations

import socket
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
import importlib
from pathlib import Path

import pytest

_daemon_client = importlib.import_module("slopgate.daemon.client")
_daemon_protocol = importlib.import_module("slopgate.daemon.protocol")
_daemon_server = importlib.import_module("slopgate.daemon.server")

DaemonRequest = _daemon_protocol.DaemonRequest
DaemonResponse = _daemon_protocol.DaemonResponse
HookDaemonServer = _daemon_server.HookDaemonServer
send_daemon_request = _daemon_client.send_daemon_request

pytestmark = pytest.mark.skipif(
    not hasattr(socket, "AF_UNIX"), reason="resident daemon transport uses Unix sockets"
)

SOCKET_WAIT_TIMEOUT_SECONDS = 2.0
SOCKET_WAIT_INTERVAL_SECONDS = 0.01
SERVER_JOIN_TIMEOUT_SECONDS = 2.0
SOCKET_READ_BYTES = 4096


@dataclass(slots=True)
class _ObservedHookRequest:
    command: object
    platform: str | None
    event: str | None
    source: object


class _EchoObservedHookRequest:
    def __call__(self, request: DaemonRequest) -> DaemonResponse:
        observed = _ObservedHookRequest(
            command=request.payload.get("command"),
            platform=request.platform,
            event=request.event,
            source=request.metadata.get("source"),
        )
        return DaemonResponse(ok=True, output=asdict(observed))


class _ExplodingHookRequestHandler:
    def __call__(self, _request: DaemonRequest) -> DaemonResponse:
        raise RuntimeError("handler exploded")


class _RejectingHookRequestHandler:
    def __call__(self, request: DaemonRequest) -> DaemonResponse:
        return DaemonResponse(
            ok=not bool(request.payload),
            stderr="blocked\n",
            exit_code=2,
        )


def _wait_for_socket(socket_path: Path) -> None:
    deadline = time.monotonic() + SOCKET_WAIT_TIMEOUT_SECONDS
    waiter = threading.Event()
    while time.monotonic() < deadline:
        if socket_path.exists():
            return
        waiter.wait(SOCKET_WAIT_INTERVAL_SECONDS)
    raise AssertionError(f"socket was not created: {socket_path}")


def _serve_one_request(
    socket_path: Path, response_handler: Callable[[DaemonRequest], DaemonResponse]
) -> threading.Thread:
    server = HookDaemonServer(socket_path, response_handler)
    thread = threading.Thread(target=server.serve, kwargs={"max_requests": 1})
    thread.start()
    _wait_for_socket(socket_path)
    return thread


def _send_raw_daemon_frame(socket_path: Path, frame: bytes) -> bytes:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.connect(str(socket_path))
        client.sendall(frame)
        return client.recv(SOCKET_READ_BYTES)


def _serve_raw_daemon_response(
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
    _wait_for_socket(socket_path)
    return thread


def test_daemon_request_payload_reaches_handler(tmp_path: Path) -> None:
    socket_path = tmp_path / "slopgate.sock"
    thread = _serve_one_request(socket_path, _EchoObservedHookRequest())
    response = send_daemon_request(
        socket_path,
        DaemonRequest(
            payload={"command": "pytest tests/test_example.py"},
            platform="codex",
            event="pre_tool_use",
            metadata={"source": "test"},
        ),
    )

    thread.join(timeout=SERVER_JOIN_TIMEOUT_SECONDS)
    assert response.output["command"] == "pytest tests/test_example.py", (
        "Daemon should forward the hook payload command to the resident handler"
    )
    assert response.output["platform"] == "codex", "Daemon should preserve platform"
    assert response.output["event"] == "pre_tool_use", "Daemon should preserve event"
    assert response.output["source"] == "test", (
        "Daemon should preserve request metadata"
    )


def test_daemon_serves_configured_request_count_then_cleans_socket(
    tmp_path: Path,
) -> None:
    socket_path = tmp_path / "slopgate.sock"
    thread = _serve_one_request(socket_path, _EchoObservedHookRequest())

    response = send_daemon_request(socket_path, DaemonRequest(payload={}))

    thread.join(timeout=SERVER_JOIN_TIMEOUT_SECONDS)
    assert response.ok is True, "Daemon should return successful handler responses"
    assert not thread.is_alive(), (
        "Daemon should stop after the configured request count"
    )
    assert not socket_path.exists(), (
        "Daemon should remove the socket path after shutdown"
    )


def test_daemon_returns_error_response_when_handler_fails(tmp_path: Path) -> None:
    socket_path = tmp_path / "slopgate.sock"
    thread = _serve_one_request(socket_path, _ExplodingHookRequestHandler())

    response = send_daemon_request(socket_path, DaemonRequest(payload={}))

    thread.join(timeout=SERVER_JOIN_TIMEOUT_SECONDS)
    assert not thread.is_alive(), "Daemon should stop after returning a handler error"
    assert response.ok is False, (
        "Daemon should convert handler failures into error responses"
    )
    assert response.error == "handler exploded", (
        "Daemon should surface the handler failure"
    )


def test_daemon_response_preserves_exit_code_and_stderr(tmp_path: Path) -> None:
    socket_path = tmp_path / "slopgate.sock"
    thread = _serve_one_request(socket_path, _RejectingHookRequestHandler())

    response = send_daemon_request(
        socket_path, DaemonRequest(payload={"blocked": True})
    )

    thread.join(timeout=SERVER_JOIN_TIMEOUT_SECONDS)
    assert response.stderr == "blocked\n", "Daemon response should preserve stderr text"
    assert response.exit_code == 2, "Daemon response should preserve nonzero exit code"


def test_daemon_rejects_malformed_request_frame(tmp_path: Path) -> None:
    socket_path = tmp_path / "slopgate.sock"
    thread = _serve_one_request(socket_path, _EchoObservedHookRequest())

    raw_response = _send_raw_daemon_frame(socket_path, b"{not-json}\n")

    thread.join(timeout=SERVER_JOIN_TIMEOUT_SECONDS)
    assert not thread.is_alive(), "Daemon should stop after handling a malformed frame"
    assert b'"ok":false' in raw_response, (
        "Malformed frames should return an error response"
    )
    assert b'"error"' in raw_response, (
        "Malformed frame response should include error detail"
    )


def test_daemon_client_reports_missing_socket(tmp_path: Path) -> None:
    response = send_daemon_request(tmp_path / "missing.sock", DaemonRequest(payload={}))

    assert response.ok is False, "Missing daemon socket should not look successful"
    assert response.error, (
        "Missing daemon socket should include connection failure detail"
    )


def test_daemon_refuses_to_unlink_existing_non_socket_path(tmp_path: Path) -> None:
    socket_path = tmp_path / "slopgate.sock"
    socket_path.write_text("keep me", encoding="utf-8")
    server = HookDaemonServer(socket_path, _EchoObservedHookRequest())

    with pytest.raises(FileExistsError, match="non-socket"):
        server.serve(max_requests=0)

    assert socket_path.read_text(encoding="utf-8") == "keep me", (
        "Daemon startup should not delete an existing non-socket file"
    )


def test_daemon_client_reports_malformed_response_frame(tmp_path: Path) -> None:
    socket_path = tmp_path / "slopgate.sock"
    thread = _serve_raw_daemon_response(socket_path, b"{not-json}\n")

    response = send_daemon_request(socket_path, DaemonRequest(payload={}))

    thread.join(timeout=SERVER_JOIN_TIMEOUT_SECONDS)
    assert not thread.is_alive(), "Malformed-response test server should stop"
    assert response.ok is False, "Malformed daemon responses should fail closed"
    assert response.error, "Malformed daemon response should include parse detail"
