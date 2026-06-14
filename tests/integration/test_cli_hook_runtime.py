from __future__ import annotations

import argparse
import importlib
import io
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from slopgate.cli.commands import cmd_daemon, cmd_handle
from slopgate.cli.parsers import build_parser

_hook_runtime = importlib.import_module("slopgate.cli.hook_runtime")
_cli_io = importlib.import_module("slopgate.cli.io")
default_daemon_socket_path = _hook_runtime.default_daemon_socket_path
report_cli_input_error = _cli_io.report_cli_input_error
EXPECTED_SERIAL_ENABLED = True


@dataclass(slots=True)
class _DaemonResponseStub:
    ok: bool
    output: dict[str, object] = field(default_factory=dict)
    error: str | None = None
    stderr: str | None = None
    exit_code: int = 0
    accepted: bool = False


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
    workers: int | None = None
    serial: bool | None = None

    def __init__(
        self,
        socket_path: Path,
        _handler: object,
        *,
        options: object | None = None,
    ) -> None:
        type(self).socket_path = socket_path
        type(self).workers = getattr(options, "workers", None)
        type(self).serial = getattr(options, "serial", False)

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


def test_daemon_parser_registers_concurrency_options() -> None:
    worker_args = build_parser().parse_args(["daemon", "--workers", "4"])
    serial_args = build_parser().parse_args(["daemon", "--serial"])

    assert worker_args.workers == 4, "Parser should preserve daemon worker count"
    assert serial_args.serial == EXPECTED_SERIAL_ENABLED, (
        "Parser should preserve serial daemon mode"
    )


@pytest.mark.parametrize(
    "workers",
    [
        pytest.param("0", id="zero_workers"),
        pytest.param("-1", id="negative_workers"),
    ],
)
def test_daemon_parser_rejects_non_positive_workers(workers: str) -> None:
    with pytest.raises(SystemExit) as exc_info:
        build_parser().parse_args(["daemon", "--workers", workers])

    assert exc_info.value.code != 0, "Invalid worker counts should fail parsing"


def test_daemon_parser_keeps_existing_options_with_workers() -> None:
    args = build_parser().parse_args(
        [
            "daemon",
            "--socket",
            "/tmp/slopgate.sock",
            "--max-requests",
            "2",
            "--workers",
            "3",
        ]
    )

    assert args.socket == "/tmp/slopgate.sock", "Parser should preserve socket path"
    assert args.max_requests == 2, "Parser should preserve max request limit"
    assert args.workers == 3, "Parser should preserve worker count"


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
        argparse.Namespace(
            socket="/tmp/slopgate-daemon.sock",
            max_requests=1,
            workers=3,
            serial=False,
        )
    )

    assert exit_code == 0, "Daemon command should return success after server exits"
    assert _DaemonServerStub.socket_path == Path("/tmp/slopgate-daemon.sock"), (
        "Daemon command should pass configured socket path to server"
    )
    assert _DaemonServerStub.max_requests == 1, "Daemon command should pass request cap"
    assert _DaemonServerStub.workers == 3, "Daemon command should pass worker count"
    assert _DaemonServerStub.serial is False, "Daemon command should pass serial mode"


def test_cmd_daemon_uses_default_socket(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("slopgate.daemon.server.HookDaemonServer", _DaemonServerStub)
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))

    exit_code = cmd_daemon(
        argparse.Namespace(socket="", max_requests=None, workers=None, serial=True)
    )

    assert exit_code == 0, "Daemon command should run with the default socket"
    assert _DaemonServerStub.socket_path == tmp_path / ("slopgate-hookd.sock"), (
        "Daemon command should use XDG runtime socket by default"
    )
    assert _DaemonServerStub.serial == EXPECTED_SERIAL_ENABLED, (
        "Daemon command should pass serial mode"
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


def test_cmd_handle_does_not_fallback_after_daemon_accept_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from slopgate.daemon import DAEMON_ACCEPTED_FAILURE_ERROR

    exit_code, _daemon_client = _run_handle_with_daemon(
        monkeypatch,
        {"cwd": "/tmp"},
        _DaemonResponseStub(
            ok=False,
            error=DAEMON_ACCEPTED_FAILURE_ERROR,
            stderr="daemon accepted request timed out\n",
            exit_code=1,
        ),
    )
    captured = capsys.readouterr()

    assert exit_code == 1, "Accepted daemon failures should fail closed"
    assert captured.err.endswith("daemon accepted request timed out\n"), (
        "Accepted daemon failures should preserve daemon stderr"
    )


def test_cmd_handle_fails_closed_for_accepted_daemon_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code, _daemon_client = _run_handle_with_daemon(
        monkeypatch,
        {"cwd": "workspace"},
        _DaemonResponseStub(
            ok=False,
            error="resident handler failed",
            exit_code=1,
            accepted=True,
        ),
    )
    captured = capsys.readouterr()

    accepted_error_contract = (
        exit_code,
        captured.err.endswith("resident handler failed\n"),
        captured.out,
    )
    assert accepted_error_contract == (
        1,
        True,
        "",
    ), "Accepted daemon errors should fail closed without direct fallback"
