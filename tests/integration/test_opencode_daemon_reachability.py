from __future__ import annotations

import argparse
from dataclasses import dataclass
import io
import json
import sys
from pathlib import Path

import pytest

import slopgate.daemon.paths
from slopgate.cli.commands import cmd_handle
from tests.daemon_protocol.support import (
    HAS_UNIX_SOCKETS,
    SERVER_JOIN_TIMEOUT_SECONDS,
    DaemonRequest,
    DaemonResponse,
    serve_one_request,
)

LINUX_RUNTIME_TEST_UID = "1000"
OPENCODE_DAEMON_SMOKE_CWD = "/tmp/slopgate-opencode-daemon-smoke"
OPENCODE_DAEMON_SMOKE_SESSION_ID = "opencode-daemon-smoke"
OPENCODE_STATUS_EVENT = "session.status"

pytestmark = pytest.mark.skipif(
    not HAS_UNIX_SOCKETS, reason="resident daemon transport uses Unix sockets"
)


class EchoOpenCodeRequestHandler:
    def __call__(self, request: DaemonRequest) -> DaemonResponse:
        return DaemonResponse(
            ok=True,
            output={
                "cwd": request.payload.get("cwd"),
                "event": request.event,
                "hook_event_name": request.payload.get("hook_event_name"),
                "platform": request.platform,
                "session_id": request.payload.get("session_id"),
            },
        )


@dataclass(frozen=True, slots=True)
class OpenCodeDaemonHandoffResult:
    daemon_alive: bool
    exit_code: int
    output: object


def _linux_runtime_socket_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.delenv("SLOPGATE_DAEMON_SOCKET", raising=False)
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr(slopgate.daemon.paths, "LINUX_RUNTIME_ROOT", tmp_path)
    monkeypatch.setattr(
        slopgate.daemon.paths.os,
        "getuid",
        lambda: LINUX_RUNTIME_TEST_UID,
    )
    runtime_dir = tmp_path / LINUX_RUNTIME_TEST_UID
    runtime_dir.mkdir()
    return runtime_dir / slopgate.daemon.paths.DEFAULT_DAEMON_SOCKET_NAME


def _opencode_status_payload() -> dict[str, object]:
    return {
        "cwd": OPENCODE_DAEMON_SMOKE_CWD,
        "hook_event_name": OPENCODE_STATUS_EVENT,
        "session_id": OPENCODE_DAEMON_SMOKE_SESSION_ID,
        "tool_input": {},
        "tool_name": "",
        "transcript_path": None,
    }


def _run_opencode_daemon_handoff(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> OpenCodeDaemonHandoffResult:
    socket_path = _linux_runtime_socket_path(monkeypatch, tmp_path)
    server_thread = serve_one_request(socket_path, EchoOpenCodeRequestHandler())
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(json.dumps(_opencode_status_payload())),
    )

    exit_code = cmd_handle(argparse.Namespace(platform="opencode"))

    server_thread.join(timeout=SERVER_JOIN_TIMEOUT_SECONDS)
    captured = capsys.readouterr()
    return OpenCodeDaemonHandoffResult(
        daemon_alive=server_thread.is_alive(),
        exit_code=exit_code,
        output=json.loads(captured.out),
    )


def test_opencode_handle_reaches_resident_linux_runtime_daemon(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert _run_opencode_daemon_handoff(monkeypatch, tmp_path, capsys) == (
        OpenCodeDaemonHandoffResult(
            daemon_alive=False,
            exit_code=0,
            output={
                "cwd": OPENCODE_DAEMON_SMOKE_CWD,
                "event": "handle",
                "hook_event_name": OPENCODE_STATUS_EVENT,
                "platform": "opencode",
                "session_id": OPENCODE_DAEMON_SMOKE_SESSION_ID,
            },
        )
    ), "OpenCode handle should reach daemon via Linux runtime socket fallback"
