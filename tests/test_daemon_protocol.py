from __future__ import annotations

from concurrent.futures import Future
import importlib
from pathlib import Path

from hypothesis import HealthCheck, given, settings, strategies
import pytest

from tests.daemon_protocol.support import (
    DisconnectingResponseSocket,
    EchoObservedHookRequest,
    HAS_UNIX_SOCKETS,
    HookDaemonServer,
    RaisingHookRequestHandler,
    RejectingHookRequestHandler,
    SERVER_JOIN_TIMEOUT_SECONDS,
    DaemonRequest,
    DaemonResponse,
    UnserializableHookRequestHandler,
    decode_response,
    observe_idle_daemon_response,
    observe_single_daemon_request,
    send_daemon_request,
    send_raw_daemon_frame,
    serve_one_request,
    serve_raw_daemon_response,
)

_daemon_server = importlib.import_module("slopgate.daemon.server")
_daemon_client = importlib.import_module("slopgate.daemon.client")
_daemon_protocol = importlib.import_module("slopgate.daemon.protocol")

DAEMON_CLIENT_PROPERTY_EXAMPLES = 5

pytestmark = pytest.mark.skipif(
    not HAS_UNIX_SOCKETS, reason="resident daemon transport uses Unix sockets"
)


def test_daemon_request_payload_reaches_handler(tmp_path: Path) -> None:
    socket_path = tmp_path / "slopgate.sock"
    thread = serve_one_request(socket_path, EchoObservedHookRequest())
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
    assert (response.ok, response.accepted) == (True, True), (
        "Handled daemon requests should be accepted successes"
    )


def test_daemon_serves_configured_request_count_then_cleans_socket(
    tmp_path: Path,
) -> None:
    socket_path = tmp_path / "slopgate.sock"
    thread = serve_one_request(socket_path, EchoObservedHookRequest())

    response = send_daemon_request(socket_path, DaemonRequest(payload={}))

    thread.join(timeout=SERVER_JOIN_TIMEOUT_SECONDS)
    assert response.ok is True, "Daemon should return successful handler responses"
    assert not thread.is_alive(), (
        "Daemon should stop after the configured request count"
    )
    assert not socket_path.exists(), (
        "Daemon should remove the socket path after shutdown"
    )


def test_daemon_returns_error_response_when_runtime_handler_fails(
    tmp_path: Path,
) -> None:
    observation = observe_single_daemon_request(
        tmp_path / "slopgate.sock",
        RaisingHookRequestHandler(RuntimeError("handler exploded")),
        DaemonRequest(payload={}),
    )

    assert not observation.server_alive, (
        "Daemon should stop after returning a handler error"
    )
    assert observation.response.ok is False, (
        "Daemon should convert handler failures into error responses"
    )
    assert observation.response.error == "handler exploded", (
        "Daemon should surface the handler failure"
    )
    accepted_failure_contract = (
        observation.response.ok,
        observation.response.error,
        observation.response.accepted,
    )
    assert accepted_failure_contract == (False, "handler exploded", True), (
        "Handler failures after request decoding should be accepted failures"
    )


def test_daemon_returns_error_response_when_key_handler_fails(
    tmp_path: Path,
) -> None:
    observation = observe_single_daemon_request(
        tmp_path / "slopgate.sock",
        RaisingHookRequestHandler(KeyError("missing")),
        DaemonRequest(payload={}),
    )

    assert not observation.server_alive, (
        "Daemon should stop after returning a handler error"
    )
    assert observation.response.ok is False, (
        "Daemon should convert key failures into error responses"
    )
    assert observation.response.error == "'missing'", (
        "Daemon should surface the handler failure"
    )


def test_daemon_returns_error_response_when_type_handler_fails(
    tmp_path: Path,
) -> None:
    observation = observe_single_daemon_request(
        tmp_path / "slopgate.sock",
        RaisingHookRequestHandler(TypeError("bad type")),
        DaemonRequest(payload={}),
    )

    assert not observation.server_alive, (
        "Daemon should stop after returning a handler error"
    )
    assert observation.response.ok is False, (
        "Daemon should convert type failures into error responses"
    )
    assert observation.response.error == "bad type", (
        "Daemon should surface the handler failure"
    )


def test_daemon_response_preserves_exit_code_and_stderr(tmp_path: Path) -> None:
    socket_path = tmp_path / "slopgate.sock"
    thread = serve_one_request(socket_path, RejectingHookRequestHandler())

    response = send_daemon_request(
        socket_path, DaemonRequest(payload={"blocked": True})
    )

    thread.join(timeout=SERVER_JOIN_TIMEOUT_SECONDS)
    assert response.stderr == "blocked\n", "Daemon response should preserve stderr text"
    assert response.exit_code == 2, "Daemon response should preserve nonzero exit code"
    assert (response.stderr, response.exit_code, response.accepted) == (
        "blocked\n",
        2,
        True,
    ), "Rejected handled requests should preserve block response and acceptance"


def test_daemon_response_preserves_accepted_flag() -> None:
    response = DaemonResponse(ok=False, error="blocked", accepted=True)

    decoded = decode_response(_daemon_protocol.encode_response(response))

    assert (decoded.ok, decoded.error, decoded.accepted) == (False, "blocked", True), (
        "Daemon protocol should round-trip accepted failures"
    )


def test_daemon_rejects_malformed_request_frame(tmp_path: Path) -> None:
    socket_path = tmp_path / "slopgate.sock"
    thread = serve_one_request(socket_path, EchoObservedHookRequest())

    raw_response = send_raw_daemon_frame(socket_path, b"{not-json}\n")

    thread.join(timeout=SERVER_JOIN_TIMEOUT_SECONDS)
    assert not thread.is_alive(), "Daemon should stop after handling a malformed frame"
    assert b'"ok":false' in raw_response, (
        "Malformed frames should return an error response"
    )
    assert b'"error"' in raw_response, (
        "Malformed frame response should include error detail"
    )


def test_daemon_survives_client_disconnect_before_response(tmp_path: Path) -> None:
    socket_path = tmp_path / "slopgate.sock"
    server = HookDaemonServer(socket_path, EchoObservedHookRequest())
    connection = DisconnectingResponseSocket(
        DaemonRequest(payload={"command": "pytest"}, platform="codex")
    )

    try:
        server._handle_connection(connection)
    finally:
        connection.close()

    response = decode_response(connection.response_frame)
    assert response.output == {
        "command": "pytest",
        "event": None,
        "platform": "codex",
        "source": None,
    }, "Daemon should build the handler response before tolerating disconnects"


def test_daemon_times_out_idle_client_without_hanging(tmp_path: Path) -> None:
    observation = observe_idle_daemon_response(tmp_path / "slopgate.sock")

    assert not observation.server_alive, (
        "Daemon should continue after timing out idle clients"
    )
    assert observation.response.ok is False, (
        "Idle client timeout should be returned as a failure"
    )
    assert observation.response.error == "timed out", (
        "Idle client timeout should preserve the socket timeout reason"
    )
    idle_failure_contract = (
        observation.response.ok,
        observation.response.error,
        observation.response.accepted,
    )
    assert idle_failure_contract == (False, "timed out", False), (
        "Idle clients should fail before request acceptance"
    )


def test_daemon_survives_unserializable_handler_response(tmp_path: Path) -> None:
    observation = observe_single_daemon_request(
        tmp_path / "slopgate.sock",
        UnserializableHookRequestHandler(),
        DaemonRequest(payload={"bad": True}),
    )

    assert not observation.server_alive, (
        "Daemon should stop normally after converting unserializable output"
    )
    assert observation.response.ok is False, (
        "Unserializable handler output should be returned as an error response"
    )
    serialization_failure_contract = (
        observation.response.error,
        observation.response.accepted,
    )
    assert serialization_failure_contract == (
        "daemon response serialization failed",
        True,
    ), "Unserializable handler output should be an accepted serialization failure"


def test_daemon_client_reports_missing_socket(tmp_path: Path) -> None:
    response = send_daemon_request(tmp_path / "missing.sock", DaemonRequest(payload={}))

    assert response.ok is False, "Missing daemon socket should not look successful"
    assert response.error, (
        "Missing daemon socket should include connection failure detail"
    )


@settings(
    max_examples=DAEMON_CLIENT_PROPERTY_EXAMPLES,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(strategies.from_regex(r"[a-z]{1,8}", fullmatch=True))
def test_daemon_client_missing_socket_fails_property(
    tmp_path: Path, suffix: str
) -> None:
    response = send_daemon_request(
        tmp_path / f"missing-{suffix}.sock", DaemonRequest(payload={})
    )

    assert response.ok is False, "Missing daemon sockets should fail closed"
    assert response.error, "Missing daemon socket failures should include detail"


def test_daemon_refuses_to_unlink_existing_non_socket_path(tmp_path: Path) -> None:
    socket_path = tmp_path / "slopgate.sock"
    socket_path.write_text("keep me", encoding="utf-8")
    server = HookDaemonServer(socket_path, EchoObservedHookRequest())

    with pytest.raises(FileExistsError, match="non-socket"):
        server.serve(max_requests=0)

    assert socket_path.read_text(encoding="utf-8") == "keep me", (
        "Daemon startup should not delete an existing non-socket file"
    )


def test_daemon_client_reports_malformed_response_frame(tmp_path: Path) -> None:
    socket_path = tmp_path / "slopgate.sock"
    thread = serve_raw_daemon_response(socket_path, b"{not-json}\n")

    response = send_daemon_request(socket_path, DaemonRequest(payload={}))

    thread.join(timeout=SERVER_JOIN_TIMEOUT_SECONDS)
    assert not thread.is_alive(), "Malformed-response test server should stop"
    accepted_failure_contract = (response.ok, response.error, response.accepted)
    assert accepted_failure_contract == (
        False,
        _daemon_client.DAEMON_ACCEPTED_FAILURE_ERROR,
        True,
    ), "Malformed responses after sending a request should be accepted failures"


def test_daemon_retains_only_pending_worker_futures() -> None:
    completed: Future[None] = Future()
    pending: Future[None] = Future()
    completed.set_result(None)

    retained = _daemon_server._retain_pending_futures({completed, pending})

    assert retained == {pending}, (
        "Long-lived daemon worker bookkeeping should drop completed futures"
    )
