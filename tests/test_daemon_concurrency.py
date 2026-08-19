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
from slopgate.daemon.admission import DAEMON_BUSY_ERROR
from slopgate.daemon.scheduler import DaemonServerOptions
from slopgate.lint._config import (
    get_config,
    get_quality_scope,
    load_config,
    set_config,
    set_quality_scope,
)
from slopgate.models import EngineResult
from slopgate.quality.constant_index import (
    build_project_constant_index,
    get_session_constant_index,
    set_session_constant_index,
)
from tests.daemon_protocol.support import (
    CoordinatedHookRequestHandler,
    HAS_UNIX_SOCKETS,
    HookDaemonServer,
    REQUEST_BLOCKED_OBSERVATION_SECONDS,
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
HANDLE_PLATFORM = "opencode"


@dataclass(frozen=True, slots=True)
class BusyLaneFallbackObservation:
    first_started: bool
    second_started: bool
    exit_code: int
    fallback_platform: str | None
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
    if not request_id:
        raise ValueError("request_id is required for a state probe response")
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


def test_daemon_refuses_overlapping_same_repo_requests(tmp_path: Path) -> None:
    repo = _managed_repo(tmp_path, "repo-a")
    observation = observe_serialized_request_start(
        tmp_path / "slopgate.sock",
        _daemon_request("first", repo),
        _daemon_request("second", repo),
    )

    assert observation.first_started, "First same-repo request should reach the handler"
    assert not observation.second_started_while_first_blocked, (
        "Same-repo overlap should not start while the lane is held"
    )
    assert not observation.second_started_after_release, (
        "Refused same-repo overlap should not queue behind the held lane"
    )
    assert observation.started_order == ("first",), (
        "Only the admitted same-repo request should start on the daemon"
    )
    assert observation.second_response is not None, (
        "Overlapping client should receive an immediate busy response"
    )
    assert observation.second_response.ok is False, (
        "Overlapping same-repo request should not evaluate on the daemon"
    )
    assert observation.second_response.accepted is False, (
        "Busy same-repo overlap must stay unaccepted so callers can fall back"
    )
    assert observation.second_response.error == DAEMON_BUSY_ERROR, (
        "Busy response should use the shared admission error"
    )
    assert not observation.server_alive, "Daemon should stop after two requests"


def test_daemon_refuses_overlapping_unknown_repo_requests(tmp_path: Path) -> None:
    observation = observe_serialized_request_start(
        tmp_path / "slopgate.sock",
        _daemon_request("first", None),
        _daemon_request("second", None),
    )

    assert observation.first_started, "First unknown-repo request should reach handler"
    assert not observation.second_started_while_first_blocked, (
        "Unknown-repo overlap should not start while the shared lane is held"
    )
    assert not observation.second_started_after_release, (
        "Refused unknown-repo overlap should not queue behind the held lane"
    )
    assert observation.second_response is not None, (
        "Overlapping unknown-repo client should receive a busy response"
    )
    assert observation.second_response.accepted is False, (
        "Busy unknown-repo overlap must stay unaccepted so callers can fall back"
    )
    assert observation.second_response.error == DAEMON_BUSY_ERROR, (
        "Busy unknown-repo response should use the shared admission error"
    )
    assert not observation.server_alive, "Daemon should stop after two requests"


def test_handle_falls_back_when_same_repo_lane_is_busy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = _managed_repo(tmp_path, "repo-a")
    observation = _observe_busy_lane_fallback(
        monkeypatch, tmp_path / "slopgate.sock", repo
    )

    assert observation.first_started, (
        "First same-repo request should hold the daemon repo lock"
    )
    assert observation.exit_code == 0, (
        "Unaccepted busy overlap should fall back to direct handle"
    )
    assert observation.fallback_platform == HANDLE_PLATFORM, (
        "Busy overlap should evaluate through the direct handle path"
    )
    assert not observation.second_started, (
        "Busy overlap should not start a second daemon evaluation"
    )
    assert not observation.server_alive, "Daemon should stop after the overlap is refused"


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


def _observe_busy_lane_fallback(
    monkeypatch: pytest.MonkeyPatch,
    socket_path: Path,
    repo: Path,
) -> BusyLaneFallbackObservation:
    handler = CoordinatedHookRequestHandler()
    server_thread = serve_requests(socket_path, handler, max_requests=2)
    first_responses: dict[str, object] = {}
    fallback: dict[str, str] = {}
    first_thread = threading.Thread(
        target=_send_first_request,
        args=(socket_path, _daemon_request("first", repo), first_responses),
    )
    first_thread.start()
    first_started = handler.wait_started("first", REQUEST_START_TIMEOUT_SECONDS)

    def _record_evaluate(_payload: object, *, platform: str) -> EngineResult:
        fallback["platform"] = platform
        return EngineResult(event_name=platform, output={"fallback": True})

    monkeypatch.setenv("SLOPGATE_DAEMON_SOCKET", str(socket_path))
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(json.dumps({"cwd": str(repo), "request_id": "second"})),
    )
    monkeypatch.setattr("slopgate.engine.evaluate_payload", _record_evaluate)
    exit_code = cmd_handle(argparse.Namespace(platform=HANDLE_PLATFORM))
    handler.release("first")
    second_started = handler.wait_started("second", REQUEST_BLOCKED_OBSERVATION_SECONDS)
    first_thread.join(timeout=SERVER_JOIN_TIMEOUT_SECONDS)
    server_thread.join(timeout=SERVER_JOIN_TIMEOUT_SECONDS)
    return BusyLaneFallbackObservation(
        first_started=first_started,
        second_started=second_started,
        exit_code=exit_code,
        fallback_platform=fallback.get("platform"),
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
