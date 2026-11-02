"""Generated isx plugin behavior through the V2 plugin API shape."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from slopgate._types import object_dict
from slopgate.search.opencode_scaffold import render_opencode_plugin
from tests.integration.opencode_plugin_v2_support import link_v2_dependencies

pytestmark = pytest.mark.skipif(shutil.which("bun") is None, reason="Bun is required")

_FAKE_ISX = """#!/bin/sh
printf '%s\\n' "$*" >> "$ISX_CALLS_PATH"
case "$1" in
  search) exec sleep 30 ;;
  list) printf '[]\\n' ;;
esac
"""
_RUNNER_PREAMBLE = """
import plugin from %s

const tools = {}
const asserts = []
await plugin.setup({
  session: { get: async () => ({ location: { directory: process.cwd() } }) },
  permission: { assert: async (input) => { asserts.push(input) } },
  tool: { transform: async (callback) => callback({ add: (tool) => { tools[tool.name] = tool } }) },
})
const controller = new AbortController()
const context = {
  sessionID: "session",
  agent: "build",
  messageID: "message",
  id: "call",
  signal: controller.signal,
  progress: async () => {},
}
"""


def _run_isx_plugin(tmp_path: Path, statements: str) -> dict[str, object]:
    home = tmp_path / "home"
    (home / ".config" / "isx").mkdir(parents=True)
    (home / ".config" / "isx" / "config.json").write_text("{}", encoding="utf-8")
    binary_dir = tmp_path / "bin"
    binary_dir.mkdir()
    fake_isx = binary_dir / "isx"
    fake_isx.write_text(_FAKE_ISX, encoding="utf-8")
    fake_isx.chmod(0o755)
    plugin_path = tmp_path / "isx-plugin.ts"
    plugin_path.write_text(render_opencode_plugin(), encoding="utf-8")
    runner = tmp_path / "runner.ts"
    runner.write_text(
        _RUNNER_PREAMBLE % json.dumps(plugin_path.as_uri()) + statements,
        encoding="utf-8",
    )
    link_v2_dependencies(tmp_path)
    completed = subprocess.run(
        ["bun", "run", str(runner)],
        cwd=tmp_path,
        env=os.environ
        | {
            "HOME": str(home),
            "PATH": f"{binary_dir}{os.pathsep}{os.environ['PATH']}",
            "ISX_CALLS_PATH": str(tmp_path / "isx-calls.txt"),
        },
        text=True,
        capture_output=True,
        check=False,
        timeout=20,
    )
    assert completed.returncode == 0, completed.stderr
    return object_dict(json.loads(completed.stdout))


@pytest.mark.parametrize(
    "tool_input",
    [
        pytest.param('{ target: "idx" }', id="default"),
        pytest.param('{ target: "idx", force: true }', id="model-supplied-force"),
    ],
)
def test_isx_remove_always_asserts_permission(tmp_path: Path, tool_input: str) -> None:
    observed = _run_isx_plugin(
        tmp_path,
        f"await tools.isx_remove.execute({tool_input}, context)\n"
        "process.stdout.write(JSON.stringify({ asserts: asserts.length }))\n",
    )

    assert observed["asserts"] == 1, (
        "a model-controlled argument must not skip the permission prompt"
    )


def test_isx_remove_does_not_advertise_force(tmp_path: Path) -> None:
    observed = _run_isx_plugin(
        tmp_path,
        "process.stdout.write(JSON.stringify("
        "{ properties: Object.keys(tools.isx_remove.input.properties) }))\n",
    )

    assert observed["properties"] == ["target"], (
        "the model must not be offered a permission bypass"
    )


def test_isx_command_stops_when_tool_call_is_cancelled(tmp_path: Path) -> None:
    observed = _run_isx_plugin(
        tmp_path,
        "const search = tools.isx_search.execute({ query: 'q' }, context)"
        '.then(() => "done", () => "rejected")\n'
        "setTimeout(() => controller.abort(), 200)\n"
        "const startedAt = Date.now()\n"
        "const outcome = await search\n"
        "process.stdout.write(JSON.stringify("
        "{ outcome, elapsedMs: Date.now() - startedAt }))\n",
    )

    assert observed["outcome"] == "rejected", (
        "a cancelled isx command must reject instead of reporting success"
    )
    assert isinstance(observed["elapsedMs"], int) and observed["elapsedMs"] < 10_000, (
        "context.signal must stop the running isx process"
    )
