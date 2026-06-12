from __future__ import annotations

import argparse
import importlib
import io
import json
import sys
from pathlib import Path

import pytest

from slopgate.cli.commands import cmd_daemon, cmd_handle
from slopgate.cli.parsers import build_parser

_hook_runtime = importlib.import_module("slopgate.cli.hook_runtime")
_cli_io = importlib.import_module("slopgate.cli.io")
default_daemon_socket_path = _hook_runtime.default_daemon_socket_path
report_cli_input_error = _cli_io.report_cli_input_error


class _DaemonResponseStub:
    def __init__(
        self,
        *,
        ok: bool,
        output: dict[str, object] | None = None,
        stderr: str | None = None,
        exit_code: int = 0,
    ) -> None:
        self.ok = ok
        self.output = output or {}
        self.error = None
        self.stderr = stderr
        self.exit_code = exit_code


class _DaemonClientStub:
    def __init__(self, response: _DaemonResponseStub) -> None:
        self.response = response
        self.socket_path: Path | None = None
        self.request: object | None = None

    def __call__(self, socket_path: Path, request: object) -> _DaemonResponseStub:
        self.socket_path = socket_path
        self.request = request
        return self.response


class _DaemonServerStub:
    socket_path: Path | None = None
    max_requests: int | None = None

    def __init__(self, socket_path: Path, _handler: object) -> None:
        type(self).socket_path = socket_path

    def serve(self, *, max_requests: int | None = None) -> None:
        type(self).max_requests = max_requests


def _run_handle_with_daemon(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, object],
    response: _DaemonResponseStub,
    *,
    use_env_socket: bool = True,
) -> tuple[int, _DaemonClientStub]:
    socket_path = Path("/tmp/slopgate-daemon-test.sock")
    daemon_client = _DaemonClientStub(response)
    if use_env_socket:
        monkeypatch.setenv("SLOPGATE_DAEMON_SOCKET", str(socket_path))
    monkeypatch.setattr("slopgate.daemon.send_daemon_request", daemon_client)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    exit_code = cmd_handle(argparse.Namespace(platform="codex"))
    return exit_code, daemon_client


def test_daemon_parser_registers_resident_daemon_command() -> None:
    args = build_parser().parse_args(
        ["daemon", "--socket", "/tmp/slopgate.sock", "--max-requests", "1"]
    )

    assert args.func is cmd_daemon, "Parser should attach the resident daemon command"
    assert args.socket == "/tmp/slopgate.sock", "Parser should preserve socket path"
    assert args.max_requests == 1, "Parser should preserve max request limit"


def test_daemon_parser_allows_default_socket() -> None:
    args = build_parser().parse_args(["daemon"])

    assert args.func is cmd_daemon, "Parser should attach daemon command without socket"
    assert args.socket is None, (
        "Parser should leave socket unset for default resolution"
    )


def test_report_cli_input_error_handles_invalid_handle_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "stdin", io.StringIO("{"))

    exit_code = cmd_handle(argparse.Namespace(platform="codex"))
    captured = capsys.readouterr()

    assert callable(report_cli_input_error)
    assert exit_code == 1, "Invalid hook JSON should fail through CLI input reporting"
    assert "Invalid JSON on stdin" in captured.err, (
        "Invalid hook JSON should emit a user-facing parse error"
    )


def test_cmd_daemon_runs_socket_server(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("slopgate.daemon.server.HookDaemonServer", _DaemonServerStub)

    exit_code = cmd_daemon(
        argparse.Namespace(socket="/tmp/slopgate-daemon.sock", max_requests=1)
    )

    assert exit_code == 0, "Daemon command should return success after server exits"
    assert _DaemonServerStub.socket_path == Path("/tmp/slopgate-daemon.sock"), (
        "Daemon command should pass configured socket path to server"
    )
    assert _DaemonServerStub.max_requests == 1, "Daemon command should pass request cap"


def test_cmd_daemon_uses_default_socket(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("slopgate.daemon.server.HookDaemonServer", _DaemonServerStub)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))

    exit_code = cmd_daemon(argparse.Namespace(socket="", max_requests=None))

    assert exit_code == 0, "Daemon command should run with the default socket"
    assert _DaemonServerStub.socket_path == tmp_path / ("slopgate-hookd.sock"), (
        "Daemon command should use XDG runtime socket by default"
    )


def test_cmd_handle_uses_configured_resident_daemon(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, daemon_client = _run_handle_with_daemon(
        monkeypatch,
        {"command": "pytest tests/test_example.py"},
        _DaemonResponseStub(ok=True, output={"decision": "allow"}),
    )
    captured = capsys.readouterr()

    assert exit_code == 0, "Daemon-backed handle should return daemon exit code"
    assert json.loads(captured.out) == {"decision": "allow"}, (
        "Daemon-backed handle should emit daemon output as hook JSON"
    )
    assert daemon_client.socket_path == Path("/tmp/slopgate-daemon-test.sock"), (
        "Handle should connect to env socket"
    )


def test_cmd_handle_preserves_daemon_request_platform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _exit_code, daemon_client = _run_handle_with_daemon(
        monkeypatch,
        {"command": "pytest tests/test_example.py"},
        _DaemonResponseStub(ok=True, output={"decision": "allow"}),
    )

    assert getattr(daemon_client.request, "payload") == {
        "command": "pytest tests/test_example.py"
    }, "Handle should preserve payload in daemon request"
    assert getattr(daemon_client.request, "platform") == "codex", (
        "Handle should preserve normalized platform in daemon request"
    )
    assert getattr(daemon_client.request, "event") == "handle", (
        "Handle should preserve event in daemon request"
    )


def test_cmd_handle_uses_default_socket_when_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("SLOPGATE_DAEMON_SOCKET", raising=False)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    default_daemon_socket_path().touch()

    _exit_code, daemon_client = _run_handle_with_daemon(
        monkeypatch,
        {"command": "pytest tests/test_example.py"},
        _DaemonResponseStub(ok=True, output={"decision": "allow"}),
        use_env_socket=False,
    )

    assert daemon_client.socket_path == tmp_path / ("slopgate-hookd.sock"), (
        "Handle should use the standard daemon socket when it exists"
    )


def test_cmd_handle_preserves_daemon_stderr_and_exit_code(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, _daemon_client = _run_handle_with_daemon(
        monkeypatch,
        {"cwd": "/tmp"},
        _DaemonResponseStub(ok=True, stderr="blocked\n", exit_code=2),
    )
    captured = capsys.readouterr()

    assert exit_code == 2, "Handle should preserve daemon nonzero exit code"
    assert captured.err.endswith("blocked\n"), "Handle should preserve daemon stderr"
    assert captured.out == "", "Daemon stderr-only blocks should not emit hook JSON"
