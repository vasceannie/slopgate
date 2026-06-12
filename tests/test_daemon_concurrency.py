from __future__ import annotations

import argparse
import io
import json
import sys
import threading
from dataclasses import dataclass
from pathlib import Path

import pytest

from slopgate.cli.commands import cmd_handle
from slopgate.constants import LINT_SCOPE_ALL
from slopgate.daemon.scheduler import DaemonServerOptions
from slopgate.lint._config import (
    get_config,
    get_quality_scope,
    load_config,
    set_config,
    set_quality_scope,
)
from slopgate.quality.constant_index import (
    build_project_constant_index,
    get_session_constant_index,
    set_session_constant_index,
)
from tests.daemon_protocol.support import (
    CoordinatedHookRequestHandler,
    HAS_UNIX_SOCKETS,
    HookDaemonServer,
    REQUEST_START_TIMEOUT_SECONDS,
    SERVER_JOIN_TIMEOUT_SECONDS,
    DaemonRequest,
    DaemonResponse,
    observe_parallel_request_start,
    observe_serialized_request_start,
    send_daemon_request,
    serve_requests,
    wait_for_socket,
)

pytestmark = pytest.mark.skipif(
    not HAS_UNIX_SOCKETS, reason="resident daemon transport uses Unix sockets"
)

SHORT_DAEMON_TIMEOUT_SECONDS = 0.05
EXPECTED_FAILURE_EXIT_CODE = 1


@dataclass(frozen=True, slots=True)
class TimeoutFallbackObservation:
    first_started: bool
    second_started: bool
    exit_code: int
    stderr: str
    server_alive: bool


@dataclass(frozen=True, slots=True)
class RequestContextObservation:
    first_project_root: object
    second_project_root: object
    second_quality_scope: object
    second_has_constant_index: object
    server_alive: bool


def _managed_repo(tmp_path: Path, name: str) -> Path:
    repo = tmp_path / name
    repo.mkdir()
    (repo / "slopgate.toml").write_text("[rules]\n", encoding="utf-8")
    return repo


def _daemon_request(request_id: str, cwd: Path | None) -> DaemonRequest:
    payload: dict[str, object] = {"request_id": request_id}
    if cwd is not None:
        payload["cwd"] = str(cwd)
    return DaemonRequest(payload=payload, platform="opencode", event="handle")


def _send_first_request(
    socket_path: Path,
    request: DaemonRequest,
    responses: dict[str, object],
) -> None:
    responses["first"] = send_daemon_request(
        socket_path, request, timeout=SERVER_JOIN_TIMEOUT_SECONDS
    )


class RequestStateProbeHandler:
    def __init__(self, first_root: Path) -> None:
        self._first_root = first_root.resolve()

    def __call__(self, request: DaemonRequest) -> DaemonResponse:
        request_id = request.payload.get("request_id")
        if request_id == "first":
            cfg = load_config(self._first_root)
            set_config(cfg)
            _ = set_quality_scope(LINT_SCOPE_ALL)
            set_session_constant_index(build_project_constant_index(self._first_root))
            return _state_response("first", cfg.project_root, LINT_SCOPE_ALL, True)
        observed_config = get_config()
        return _state_response(
            "second",
            observed_config.project_root,
            get_quality_scope(),
            get_session_constant_index() is not None,
        )


def _state_response(
    request_id: str,
    project_root: Path,
    quality_scope: str | None,
    has_constant_index: bool,
) -> DaemonResponse:
    return DaemonResponse(
        ok=True,
        output={
            "request_id": request_id,
            "project_root": str(project_root),
            "quality_scope": quality_scope,
            "has_constant_index": has_constant_index,
        },
    )


def test_daemon_allows_different_repos_to_evaluate_concurrently(
    tmp_path: Path,
) -> None:
    observation = observe_parallel_request_start(
        tmp_path / "slopgate.sock",
        _daemon_request("first", _managed_repo(tmp_path, "repo-a")),
        _daemon_request("second", _managed_repo(tmp_path, "repo-b")),
    )

    assert observation.first_started, "First repo request should reach the handler"
    assert observation.second_started_while_first_blocked, (
        "Different repo requests should start before the first repo is released"
    )
    assert observation.first_response is not None, "First client should get a response"
    assert observation.second_response is not None, (
        "Second client should get a response"
    )
    assert observation.first_response.output["request_id"] == "first", (
        "First client should receive its own response"
    )
    assert observation.second_response.output["request_id"] == "second", (
        "Second client should receive its own response"
    )
    assert not observation.server_alive, "Daemon should stop after two requests"


def test_daemon_serializes_requests_for_same_repo(tmp_path: Path) -> None:
    repo = _managed_repo(tmp_path, "repo-a")
    observation = observe_serialized_request_start(
        tmp_path / "slopgate.sock",
        _daemon_request("first", repo),
        _daemon_request("second", repo),
    )

    assert observation.first_started, "First same-repo request should reach the handler"
    assert not observation.second_started_while_first_blocked, (
        "Same-repo request should not start while the first request is blocked"
    )
    assert observation.second_started_after_release, (
        "Second same-repo request should start after the first request is released"
    )
    assert observation.started_order == ("first", "second"), (
        "Same-repo requests should preserve arrival order"
    )
    assert not observation.server_alive, "Daemon should stop after two requests"


def test_daemon_serializes_unknown_repo_requests(tmp_path: Path) -> None:
    observation = observe_serialized_request_start(
        tmp_path / "slopgate.sock",
        _daemon_request("first", None),
        _daemon_request("second", None),
    )

    assert observation.first_started, "First unknown-repo request should reach handler"
    assert not observation.second_started_while_first_blocked, (
        "Unknown-repo requests should share one serialized lane"
    )
    assert observation.second_started_after_release, (
        "Second unknown-repo request should start after the first request is released"
    )
    assert not observation.server_alive, "Daemon should stop after two requests"


def test_handle_does_not_direct_fallback_after_same_repo_daemon_timeout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = _managed_repo(tmp_path, "repo-a")
    observation = _observe_timeout_fallback(
        monkeypatch, capsys, tmp_path / "slopgate.sock", repo
    )

    assert observation.first_started, (
        "First same-repo request should hold the daemon repo lock"
    )
    assert observation.exit_code == EXPECTED_FAILURE_EXIT_CODE, (
        "Accepted daemon timeouts should fail closed instead of falling back"
    )
    assert observation.second_started, (
        "Timed-out accepted request should still finish in daemon"
    )
    assert not observation.server_alive, "Daemon should stop after both requests finish"
    assert "daemon request accepted" in observation.stderr, (
        "Accepted timeout should explain why direct fallback was skipped"
    )


def test_daemon_resets_request_context_between_single_worker_requests(
    tmp_path: Path,
) -> None:
    first_repo = _managed_repo(tmp_path, "repo-a")
    second_repo = _managed_repo(tmp_path, "repo-b")
    observation = _observe_single_worker_request_context(
        tmp_path / "slopgate.sock", first_repo, second_repo
    )

    assert observation.first_project_root == str(first_repo.resolve()), (
        "First request should set repo-local lint config"
    )
    assert observation.second_project_root != str(first_repo.resolve()), (
        "Second request on reused worker should not inherit first repo config"
    )
    assert observation.second_quality_scope is None, (
        "Second request should not inherit first request quality scope"
    )
    assert observation.second_has_constant_index is False, (
        "Second request should not inherit first request constant index"
    )
    assert not observation.server_alive, "Single-worker daemon should stop cleanly"


def _short_timeout_request(socket_path: Path, request: DaemonRequest) -> DaemonResponse:
    return send_daemon_request(
        socket_path,
        request,
        timeout=SHORT_DAEMON_TIMEOUT_SECONDS,
    )


def _forbidden_evaluate(_payload: object, *, platform: str) -> object:
    raise AssertionError(f"direct fallback should not run for {platform}")


def _observe_timeout_fallback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    socket_path: Path,
    repo: Path,
) -> TimeoutFallbackObservation:
    handler = CoordinatedHookRequestHandler()
    server_thread = serve_requests(socket_path, handler, max_requests=2)
    first_responses: dict[str, object] = {}
    first_thread = threading.Thread(
        target=_send_first_request,
        args=(socket_path, _daemon_request("first", repo), first_responses),
    )
    first_thread.start()
    first_started = handler.wait_started("first", REQUEST_START_TIMEOUT_SECONDS)
    monkeypatch.setenv("SLOPGATE_DAEMON_SOCKET", str(socket_path))
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(json.dumps({"cwd": str(repo), "request_id": "second"})),
    )
    monkeypatch.setattr("slopgate.daemon.send_daemon_request", _short_timeout_request)
    monkeypatch.setattr("slopgate.engine.evaluate_payload", _forbidden_evaluate)
    exit_code = cmd_handle(argparse.Namespace(platform="opencode"))
    handler.release("first")
    second_started = handler.wait_started("second", REQUEST_START_TIMEOUT_SECONDS)
    handler.release("second")
    first_thread.join(timeout=SERVER_JOIN_TIMEOUT_SECONDS)
    server_thread.join(timeout=SERVER_JOIN_TIMEOUT_SECONDS)
    return TimeoutFallbackObservation(
        first_started=first_started,
        second_started=second_started,
        exit_code=exit_code,
        stderr=capsys.readouterr().err,
        server_alive=server_thread.is_alive(),
    )


def _observe_single_worker_request_context(
    socket_path: Path, first_repo: Path, second_repo: Path
) -> RequestContextObservation:
    server = HookDaemonServer(
        socket_path,
        RequestStateProbeHandler(first_repo),
        options=DaemonServerOptions(workers=1),
    )
    server_thread = threading.Thread(target=server.serve, kwargs={"max_requests": 2})
    server_thread.start()
    wait_for_socket(socket_path)
    first_response = send_daemon_request(
        socket_path, _daemon_request("first", first_repo)
    )
    second_response = send_daemon_request(
        socket_path, _daemon_request("second", second_repo)
    )
    server_thread.join(timeout=SERVER_JOIN_TIMEOUT_SECONDS)
    return RequestContextObservation(
        first_project_root=first_response.output["project_root"],
        second_project_root=second_response.output["project_root"],
        second_quality_scope=second_response.output["quality_scope"],
        second_has_constant_index=second_response.output["has_constant_index"],
        server_alive=server_thread.is_alive(),
    )
