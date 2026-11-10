"""Hook input decoding and daemon transport availability on Windows-like hosts."""

from __future__ import annotations

import argparse
import io
import json
import socket
import sys

import pytest

from slopgate.cli.commands import cmd_handle
from slopgate.cli.io import CliInputError, load_stdin_json

_NON_ASCII_CWD = "/work/projāect"
_BOM = b"\xef\xbb\xbf"
_UTF8_PAYLOAD = json.dumps({"cwd": _NON_ASCII_CWD}, ensure_ascii=False).encode()
# Windows pipes default stdin to the ANSI code page, where byte 0x81 of "ā" is undefined.
_WINDOWS_PIPE_ENCODING = "cp1252"


def _pipe_stdin(monkeypatch: pytest.MonkeyPatch, raw: bytes) -> None:
    stdin = io.TextIOWrapper(io.BytesIO(raw), _WINDOWS_PIPE_ENCODING)
    monkeypatch.setattr(sys, "stdin", stdin)


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param(_UTF8_PAYLOAD, id="utf-8"),
        pytest.param(_BOM + _UTF8_PAYLOAD, id="utf-8-bom"),
    ],
)
def test_load_stdin_json_decodes_utf8_despite_legacy_code_page(
    monkeypatch: pytest.MonkeyPatch, raw: bytes
) -> None:
    _pipe_stdin(monkeypatch, raw)

    assert load_stdin_json() == {"cwd": _NON_ASCII_CWD}, (
        "hook payload bytes are UTF-8 JSON regardless of the locale code page"
    )


_INVALID_PREFIX = b'{"cwd": "'
_INVALID_UTF8_PAYLOAD = _INVALID_PREFIX + b'\xff"}'


def test_cmd_handle_reports_invalid_utf8_as_input_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _pipe_stdin(monkeypatch, _INVALID_UTF8_PAYLOAD)

    exit_code = cmd_handle(argparse.Namespace(platform="codex"))

    assert exit_code == 1, "undecodable hook input must fail as a CLI input error"
    assert "Invalid UTF-8 on stdin" in capsys.readouterr().err, (
        "undecodable hook input must name the encoding problem"
    )


@pytest.mark.parametrize(
    ("raw", "offset"),
    [
        pytest.param(_INVALID_UTF8_PAYLOAD, len(_INVALID_PREFIX), id="no-bom"),
        pytest.param(
            _BOM + _INVALID_UTF8_PAYLOAD, len(_BOM + _INVALID_PREFIX), id="utf-8-bom"
        ),
    ],
)
def test_load_stdin_json_reports_raw_stdin_offset_of_invalid_utf8(
    monkeypatch: pytest.MonkeyPatch, raw: bytes, offset: int
) -> None:
    _pipe_stdin(monkeypatch, raw)

    with pytest.raises(CliInputError, match=f"at byte {offset}:"):
        _ = load_stdin_json()


class _InProcessEngineStub:
    """Stands in for evaluate_payload so the test observes the in-process path."""

    def __init__(self, _payload: object, platform: str) -> None:
        self.output: dict[str, object] = {"engine": platform}


def _host_without_unix_sockets(monkeypatch: pytest.MonkeyPatch) -> None:
    """Configure a daemon socket on a Python build that lacks AF_UNIX."""
    monkeypatch.delattr(socket, "AF_UNIX", raising=False)
    monkeypatch.setenv("SLOPGATE_DAEMON_SOCKET", "/tmp/slopgate-daemon-test.sock")
    monkeypatch.setattr("slopgate.engine.evaluate_payload", _InProcessEngineStub)
    _pipe_stdin(monkeypatch, json.dumps({"cwd": "workspace"}).encode())


def test_cmd_handle_falls_back_in_process_without_unix_sockets(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _host_without_unix_sockets(monkeypatch)

    exit_code = cmd_handle(argparse.Namespace(platform="codex"))

    assert (exit_code, capsys.readouterr().out) == (0, '{"engine":"codex"}\n'), (
        "a configured daemon socket must not stop evaluation where AF_UNIX is absent"
    )
