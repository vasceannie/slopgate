from __future__ import annotations

import json
import os
import shlex
import shutil
import socket
import subprocess
import threading
from pathlib import Path

import pytest

from slopgate.installer.hook_proxy import (
    HOOK_PROXY_MARKER,
    NODE_DAEMON_CLIENT_SCRIPT,
    NODE_DAEMON_TIMEOUT_MS,
)
import slopgate.installer._shared
from tests.daemon_protocol.support import SERVER_JOIN_TIMEOUT_SECONDS, wait_for_socket

ACCEPTED_PROXY_FAILURE_EXIT_CODE = 7
HAS_NODE_RUNTIME = shutil.which("node") is not None
HAS_UNIX_SOCKETS = hasattr(socket, "AF_UNIX")
NODE_SCRIPT_TIMEOUT_SECONDS = 5
PROXY_FALLBACK_EXIT_CODE = 75
SHORT_NODE_TIMEOUT_MS = 50
SOCKET_READ_BYTES = 4096


def _run_node_proxy(
    socket_path: Path,
    payload: dict[str, object],
    *,
    node_script: str = NODE_DAEMON_CLIENT_SCRIPT,
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "SLOPGATE_DAEMON_SOCKET": str(socket_path)}
    return subprocess.run(
        ["node", "-e", node_script],
        input=json.dumps(payload),
        capture_output=True,
        env=env,
        text=True,
        timeout=NODE_SCRIPT_TIMEOUT_SECONDS,
    )


def _serve_proxy_response(
    socket_path: Path, response: dict[str, object]
) -> threading.Thread:
    target = str(socket_path)

    def serve_response() -> None:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server_socket:
            server_socket.bind(target)
            server_socket.listen()
            connection, _ = server_socket.accept()
            with connection:
                _ = connection.recv(SOCKET_READ_BYTES)
                frame = json.dumps(response).encode("utf-8") + b"\n"
                connection.sendall(frame)

    thread = threading.Thread(target=serve_response)
    thread.start()
    wait_for_socket(socket_path)
    return thread


def _serve_proxy_without_response(
    socket_path: Path,
    release: threading.Event,
) -> threading.Thread:
    target = str(socket_path)

    def hold_connection() -> None:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server_socket:
            server_socket.bind(target)
            server_socket.listen()
            connection, _ = server_socket.accept()
            with connection:
                _ = connection.recv(SOCKET_READ_BYTES)
                release.wait(timeout=NODE_SCRIPT_TIMEOUT_SECONDS)

    thread = threading.Thread(target=hold_connection)
    thread.start()
    wait_for_socket(socket_path)
    return thread


def _run_accepted_timeout_proxy(socket_path: Path) -> subprocess.CompletedProcess[str]:
    release = threading.Event()
    thread = _serve_proxy_without_response(socket_path, release)
    short_timeout_script = NODE_DAEMON_CLIENT_SCRIPT.replace(
        f"client.setTimeout({NODE_DAEMON_TIMEOUT_MS})",
        f"client.setTimeout({SHORT_NODE_TIMEOUT_MS})",
    )
    try:
        return _run_node_proxy(
            socket_path,
            {"hook_event_name": "PreToolUse"},
            node_script=short_timeout_script,
        )
    finally:
        release.set()
        thread.join(timeout=SERVER_JOIN_TIMEOUT_SECONDS)
        assert not thread.is_alive(), "Proxy timeout server should release cleanly"


def test_posix_hook_command_uses_daemon_proxy_with_python_fallback() -> None:
    command = slopgate.installer._shared.hook_command(
        "/opt/slopgate/bin/slopgate", "handle", "--platform", "codex", windows=False
    )
    argv = shlex.split(command)

    assert argv[:3] == ["/bin/sh", "-c", argv[2]], (
        "POSIX hook command should run through a shell proxy"
    )
    assert HOOK_PROXY_MARKER in argv[2], (
        "Proxy script should include the managed Slopgate marker"
    )
    assert "node -e" in argv[2], "Proxy should attempt the Node daemon client first"
    assert '"$@" < "$tmp"' in argv[2], (
        "Proxy should fall back to the original Slopgate invocation with buffered stdin"
    )
    assert argv[3:] == [
        "slopgate-hook",
        "/opt/slopgate/bin/slopgate",
        "handle",
        "--platform",
        "codex",
    ], "Proxy should preserve the original fallback argv"


def test_node_daemon_client_preserves_empty_stdin_noop() -> None:
    assert "if(!text.trim())process.exit(0)" in NODE_DAEMON_CLIENT_SCRIPT, (
        "Daemon proxy should preserve direct slopgate handle no-op behavior for empty stdin"
    )


def test_node_daemon_client_uses_unknown_when_platform_env_is_absent() -> None:
    assert "SLOPGATE_HOOK_PLATFORM||'unknown'" in NODE_DAEMON_CLIENT_SCRIPT, (
        "Daemon proxy should not invent Claude provenance when platform env is absent"
    )
    assert "SLOPGATE_HOOK_PLATFORM||'claude'" not in NODE_DAEMON_CLIENT_SCRIPT, (
        "Daemon proxy should avoid the old false-Claude fallback"
    )


def test_node_daemon_client_uses_configured_daemon_timeout() -> None:
    assert (
        f"client.setTimeout({NODE_DAEMON_TIMEOUT_MS})" in NODE_DAEMON_CLIENT_SCRIPT
    ), "Node daemon proxy should share the Python daemon client timeout"


def test_node_daemon_client_fails_closed_after_accepted_response() -> None:
    accepted_contract = (
        "response.accepted" in NODE_DAEMON_CLIENT_SCRIPT,
        "process.exit(Number(response.exit_code)||1)" in NODE_DAEMON_CLIENT_SCRIPT,
        "process.exit(75)" in NODE_DAEMON_CLIENT_SCRIPT,
    )

    assert accepted_contract == (True, True, True), (
        "Node daemon proxy should fail closed for accepted errors while preserving fallback sentinel"
    )


@pytest.mark.skipif(
    not HAS_NODE_RUNTIME, reason="Node runtime required for proxy script"
)
@pytest.mark.skipif(not HAS_UNIX_SOCKETS, reason="POSIX proxy uses Unix sockets")
def test_node_daemon_client_executes_accepted_failure_contract(tmp_path: Path) -> None:
    socket_path = tmp_path / "slopgate.sock"
    thread = _serve_proxy_response(
        socket_path,
        {
            "accepted": True,
            "exit_code": ACCEPTED_PROXY_FAILURE_EXIT_CODE,
            "ok": False,
            "output": {},
            "stderr": "blocked\n",
        },
    )

    result = _run_node_proxy(socket_path, {"hook_event_name": "PreToolUse"})
    thread.join(timeout=SERVER_JOIN_TIMEOUT_SECONDS)

    assert not thread.is_alive(), "Proxy response server should handle one request"
    assert result.returncode == ACCEPTED_PROXY_FAILURE_EXIT_CODE, (
        "Accepted daemon failures should preserve daemon exit code"
    )
    assert result.stderr == "blocked\n", (
        "Accepted daemon failures should preserve daemon stderr"
    )


@pytest.mark.skipif(
    not HAS_NODE_RUNTIME, reason="Node runtime required for proxy script"
)
@pytest.mark.skipif(not HAS_UNIX_SOCKETS, reason="POSIX proxy uses Unix sockets")
def test_node_daemon_client_executes_unaccepted_fallback_contract(
    tmp_path: Path,
) -> None:
    socket_path = tmp_path / "slopgate.sock"
    thread = _serve_proxy_response(
        socket_path,
        {
            "accepted": False,
            "error": "not admitted",
            "ok": False,
            "output": {},
        },
    )

    result = _run_node_proxy(socket_path, {"hook_event_name": "PreToolUse"})
    thread.join(timeout=SERVER_JOIN_TIMEOUT_SECONDS)

    assert not thread.is_alive(), "Proxy response server should handle one request"
    assert result.returncode == PROXY_FALLBACK_EXIT_CODE, (
        "Unaccepted daemon failures should return the fallback sentinel"
    )
    assert result.stderr == "", "Fallback sentinel should not emit daemon error text"


@pytest.mark.skipif(
    not HAS_NODE_RUNTIME, reason="Node runtime required for proxy script"
)
@pytest.mark.skipif(not HAS_UNIX_SOCKETS, reason="POSIX proxy uses Unix sockets")
def test_node_daemon_client_falls_back_when_socket_connection_fails(
    tmp_path: Path,
) -> None:
    result = _run_node_proxy(
        tmp_path / "missing.sock",
        {"hook_event_name": "PreToolUse"},
    )

    assert result.returncode == PROXY_FALLBACK_EXIT_CODE, (
        "Daemon connection failures before request admission should allow direct fallback"
    )
    assert result.stderr == "", (
        "Pre-admission fallback should not report a daemon-owned failure"
    )


@pytest.mark.skipif(
    not HAS_NODE_RUNTIME, reason="Node runtime required for proxy script"
)
@pytest.mark.skipif(not HAS_UNIX_SOCKETS, reason="POSIX proxy uses Unix sockets")
def test_node_daemon_client_fails_closed_after_accepted_timeout(
    tmp_path: Path,
) -> None:
    result = _run_accepted_timeout_proxy(tmp_path / "slopgate.sock")

    assert result.returncode == 1, (
        "Daemon timeouts after request admission should fail closed instead of falling back"
    )
    assert (
        "daemon request accepted but response unavailable: timed out" in result.stderr
    )


@pytest.mark.skipif(
    not HAS_NODE_RUNTIME, reason="Node runtime required for proxy script"
)
@pytest.mark.skipif(not HAS_UNIX_SOCKETS, reason="POSIX proxy uses Unix sockets")
def test_node_daemon_client_falls_back_when_acceptance_is_missing(
    tmp_path: Path,
) -> None:
    socket_path = tmp_path / "slopgate.sock"
    thread = _serve_proxy_response(
        socket_path,
        {
            "error": "admission not confirmed",
            "ok": False,
            "output": {},
        },
    )

    result = _run_node_proxy(socket_path, {"hook_event_name": "PreToolUse"})
    thread.join(timeout=SERVER_JOIN_TIMEOUT_SECONDS)

    assert not thread.is_alive(), "Proxy response server should handle one request"
    assert result.returncode == PROXY_FALLBACK_EXIT_CODE, (
        "Missing acceptance acknowledgement should preserve direct CLI fallback"
    )
    assert result.stderr == "", (
        "Unacknowledged fallback should not emit daemon error text"
    )


def test_posix_hook_command_is_owned_by_slopgate() -> None:
    command = slopgate.installer._shared.hook_command(
        "slopgate", "handle", windows=False
    )

    assert slopgate.installer._shared.command_is_slopgate_hook(command), (
        "Owned-hook detection should recognize the daemon proxy wrapper"
    )


def test_windows_hook_command_keeps_direct_powershell_invocation() -> None:
    command = slopgate.installer._shared.hook_command(
        "C:\\Tools\\slopgate.exe", "handle", windows=True
    )

    assert command.startswith("powershell.exe"), (
        "Windows hooks should keep the direct PowerShell command path"
    )
    assert HOOK_PROXY_MARKER not in command, (
        "Windows hooks should not use the POSIX daemon proxy"
    )
