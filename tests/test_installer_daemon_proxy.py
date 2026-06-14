from __future__ import annotations

import shlex

from slopgate.installer.hook_proxy import HOOK_PROXY_MARKER, NODE_DAEMON_CLIENT_SCRIPT
import slopgate.installer._shared


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
