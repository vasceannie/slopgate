"""POSIX daemon proxy command generation for installed hooks."""

from __future__ import annotations

import shlex
from typing import Protocol

from slopgate.constants import PLATFORM_CLAUDE
from slopgate.daemon.paths import DEFAULT_DAEMON_SOCKET_NAME

HOOK_PROXY_MARKER = "SLOPGATE_DAEMON_PROXY=1"
NODE_DAEMON_CLIENT_SCRIPT = (
    "const fs=require('fs'),net=require('net');"
    "const text=fs.readFileSync(0,'utf8');if(!text.trim())process.exit(0);"
    "let payload={};"
    "try{payload=text.trim()?JSON.parse(text):{};}catch(e){"
    "fs.writeSync(2,'Invalid JSON on stdin: '+e.message+'\\n');process.exit(1)}"
    "const req=JSON.stringify({payload,platform:process.env.SLOPGATE_HOOK_PLATFORM||"
    f"{PLATFORM_CLAUDE!r},event:'handle'}})+'\\n';"
    "const sock=process.env.SLOPGATE_DAEMON_SOCKET;let data='';"
    "const client=net.createConnection(sock);client.setTimeout(1000);"
    "client.on('connect',()=>client.end(req));"
    "client.on('data',chunk=>data+=chunk);"
    "client.on('timeout',()=>process.exit(75));"
    "client.on('error',()=>process.exit(75));"
    "client.on('end',()=>{try{const response=JSON.parse(data);"
    "if(!response.ok)process.exit(75);"
    "if(response.stderr)fs.writeSync(2,String(response.stderr));"
    "if(response.output&&Object.keys(response.output).length)"
    "fs.writeSync(1,JSON.stringify(response.output)+'\\n');"
    "process.exit(Number(response.exit_code)||0)}catch(e){process.exit(75)}});"
)


class _ShellCommandBuilder(Protocol):
    def __call__(self, argv: list[str], *, windows: bool | None = None) -> str: ...


def posix_daemon_proxy_command(
    fallback_argv: list[str],
    platform: str,
    shell_command: _ShellCommandBuilder,
) -> str:
    if not fallback_argv:
        raise ValueError("fallback argv is required for hook proxy")
    proxy_argv = [
        "/bin/sh",
        "-c",
        _posix_daemon_proxy_script(platform),
        "slopgate-hook",
        *fallback_argv,
    ]
    return shell_command(proxy_argv, windows=False)


def _posix_daemon_proxy_script(platform: str) -> str:
    node_script = shlex.quote(NODE_DAEMON_CLIENT_SCRIPT)
    platform_value = shlex.quote(platform)
    socket_name = shlex.quote(DEFAULT_DAEMON_SOCKET_NAME)
    return "\n".join(
        [
            HOOK_PROXY_MARKER,
            'tmp="${TMPDIR:-/tmp}/slopgate-hook.$$"',
            'cleanup() { rm -f "$tmp"; }',
            "trap cleanup EXIT HUP INT TERM",
            'cat > "$tmp" || exit 1',
            'sock="${SLOPGATE_DAEMON_SOCKET:-}"',
            'if [ -z "$sock" ]; then',
            '  if [ -n "${XDG_RUNTIME_DIR:-}" ]; then',
            f'    sock="${{XDG_RUNTIME_DIR}}/{socket_name}"',
            "  else",
            '    uid="$(id -u 2>/dev/null || printf user)"',
            '    sock="${TMPDIR:-/tmp}/slopgate-hookd-${uid}.sock"',
            "  fi",
            "fi",
            'if [ -S "$sock" ] && command -v node >/dev/null 2>&1; then',
            '  SLOPGATE_DAEMON_SOCKET="$sock" '
            f'SLOPGATE_HOOK_PLATFORM={platform_value} node -e {node_script} < "$tmp"',
            "  status=$?",
            '  if [ "$status" -ne 75 ]; then exit "$status"; fi',
            "fi",
            '"$@" < "$tmp"',
        ]
    )


__all__ = [
    "HOOK_PROXY_MARKER",
    "NODE_DAEMON_CLIENT_SCRIPT",
    "posix_daemon_proxy_command",
]
