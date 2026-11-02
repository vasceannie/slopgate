"""Boot a real OpenCode server with isolated state and record what it reports."""

from __future__ import annotations

import base64
import json
import os
import re
import socket
import subprocess
import threading
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from slopgate._types import ObjectDict, object_dict, object_list
from slopgate.installer._opencode import render_opencode_plugin
from slopgate.resources import resource_path
from slopgate.search import opencode_scaffold

_BOOT_TIMEOUT_SECONDS = 60.0
_POLL_SECONDS = 0.2
_POLL_ATTEMPTS = 300
_PASSWORD_PATTERN = re.compile(r"server password (\S+)")
_PROBE_DONE_PATTERN = re.compile("slopgate-real-host-probe-done")
_PROBE_SOURCE = """
import { writeFileSync } from "node:fs"
import { Plugin } from "@opencode/plugin"

export default Plugin.define({
  id: "zz-probe",
  async setup(ctx) {
    const tools = await ctx.tool.list()
    writeFileSync(%s, JSON.stringify({
      version: ctx.app.version,
      location: ctx.location,
      tools: tools.map((tool) => ({ id: tool.id, codemode: tool.options?.codemode })),
    }))
    console.info("slopgate-real-host-probe-done")
  },
})
"""


@dataclass(frozen=True, slots=True)
class HostObservation:
    """Facts reported by the real host, not by a test double."""

    version: str
    session_directory: Path
    project_directory: Path
    plugins: dict[str, str]
    tool_codemode: dict[str, object]


def _write_plugins(config_dir: Path, probe_path: Path) -> None:
    plugins = config_dir / "opencode" / "plugins"
    (plugins / "isx-tools").mkdir(parents=True)
    (plugins / "slopgate-plugin.ts").write_text(
        render_opencode_plugin(
            resource_path("opencode_plugin.ts").read_text(encoding="utf-8"),
            str(config_dir / "slopgate-not-called"),
            {"opencode_version": "2.2.5"},
        ),
        encoding="utf-8",
    )
    (plugins / "isx-tools" / "index.ts").write_text(
        opencode_scaffold.render_opencode_plugin(), encoding="utf-8"
    )
    (plugins / "zz-probe.ts").write_text(
        _PROBE_SOURCE % json.dumps(str(probe_path)), encoding="utf-8"
    )


def _isolated_environment(root: Path) -> dict[str, str]:
    inherited = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("OPENCODE_")
    }
    return inherited | {
        "HOME": str(root / "home"),
        "XDG_CONFIG_HOME": str(root / "config"),
        "XDG_DATA_HOME": str(root / "data"),
        "XDG_STATE_HOME": str(root / "state"),
        "XDG_CACHE_HOME": str(root / "cache"),
    }


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


class RealHostServer:
    """A running `opencode serve` process whose log output can be awaited."""

    def __init__(self, root: Path, directory: Path) -> None:
        self._port = _free_port()
        self._lines: list[str] = []
        self._changed = threading.Condition()
        self._process = subprocess.Popen(
            [
                "opencode",
                "serve",
                "--hostname",
                "127.0.0.1",
                "--port",
                str(self._port),
                "--print-logs",
            ],
            cwd=directory,
            env=_isolated_environment(root),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        threading.Thread(target=self._collect_lines, daemon=True).start()

    def _collect_lines(self) -> None:
        stream = self._process.stdout
        assert stream is not None, "the server must run with a captured stdout"
        for line in stream:
            with self._changed:
                self._lines.append(line)
                self._changed.notify_all()

    def _first_match(self, pattern: re.Pattern[str]) -> re.Match[str] | None:
        matches = (pattern.search(line) for line in self._lines)
        return next((match for match in matches if match is not None), None)

    def wait_for_log(self, pattern: re.Pattern[str]) -> re.Match[str]:
        """Return the first log line match, failing after the boot timeout."""
        with self._changed:
            self._changed.wait_for(
                lambda: self._first_match(pattern) is not None,
                timeout=_BOOT_TIMEOUT_SECONDS,
            )
            match = self._first_match(pattern)
            assert match is not None, (
                f"OpenCode never logged {pattern.pattern}: {self._lines[-5:]}"
            )
            return match

    def request(self, path: str, directory: Path, method: str = "GET") -> ObjectDict:
        """Call the authenticated server API for one location."""
        password = self.wait_for_log(_PASSWORD_PATTERN).group(1)
        token = base64.b64encode(f"opencode:{password}".encode()).decode()
        request = urllib.request.Request(
            f"http://127.0.0.1:{self._port}/api/{path}?directory={directory}",
            data=b"{}" if method == "POST" else None,
            method=method,
            headers={
                "Authorization": f"Basic {token}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=_BOOT_TIMEOUT_SECONDS) as reply:
            return object_dict(json.loads(reply.read().decode("utf-8")))

    def stop(self) -> None:
        """Terminate the server and reap it."""
        self._process.terminate()
        self._process.wait(timeout=_BOOT_TIMEOUT_SECONDS)


def _plugin_statuses(server: RealHostServer, directory: Path) -> dict[str, str]:
    reply = server.request("plugin", directory)
    return {
        str(object_dict(item).get("id")): str(
            object_dict(object_dict(item).get("state")).get("status")
        )
        for item in object_list(reply.get("data"))
    }


def _active_plugins(server: RealHostServer, directory: Path) -> dict[str, str]:
    """Poll until the background plugin generation includes our plugins."""
    pause = threading.Event()
    statuses: dict[str, str] = {}
    for _attempt in range(_POLL_ATTEMPTS):
        statuses = _plugin_statuses(server, directory)
        if {"slopgate", "slopgate.isx"} <= statuses.keys():
            break
        pause.wait(_POLL_SECONDS)
    return statuses


def start_real_host(root: Path) -> tuple[RealHostServer, Path]:
    """Start OpenCode in a repo subdirectory with the generated plugins."""
    project = root / "repo"
    directory = project / "sub"
    directory.mkdir(parents=True)
    (root / "home").mkdir()
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    _write_plugins(root / "config", root / "probe.json")
    return RealHostServer(root, directory), directory


def observe_real_host(
    server: RealHostServer, directory: Path, probe_path: Path
) -> HostObservation:
    """Capture what the running host reports about plugins, tools, and sessions."""
    server.request("plugin", directory)
    server.wait_for_log(_PROBE_DONE_PATTERN)
    plugins = _active_plugins(server, directory)
    session = object_dict(server.request("session", directory, "POST")["data"])
    probe = object_dict(json.loads(probe_path.read_text(encoding="utf-8")))
    location = object_dict(probe["location"])
    return HostObservation(
        version=str(probe["version"]),
        session_directory=Path(str(object_dict(session["location"])["directory"])),
        project_directory=Path(str(object_dict(location["project"])["directory"])),
        plugins=plugins,
        tool_codemode={
            str(object_dict(tool)["id"]): object_dict(tool).get("codemode")
            for tool in object_list(probe["tools"])
        },
    )
