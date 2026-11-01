from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from slopgate._types import ObjectDict, object_dict
from slopgate.installer._opencode import render_opencode_plugin
from slopgate.resources import resource_path

_REPOSITORY_NODE_MODULES = Path(__file__).parents[2] / "node_modules"
ENABLED = "[slopgate]\nenabled = true\n"
REPAIR_REQUIRED = json.dumps(
    {
        "status": "REPAIR_REQUIRED",
        "generation": "generation-1",
        "targets": [{"rule_id": "QUALITY-LINT-001", "path": "a.py"}],
    }
)
REPAIR_CLEAN = json.dumps({"status": "CLEAN"})
ENFORCER_ALLOW = json.dumps({"action": "allow"})
# Reads the state on every status call so a test can arm repair mid-program.
_SCRIPTED_SLOPGATE = """#!/usr/bin/env python3
import os
import sys

if sys.argv[1:3] == ["repair", "status"]:
    with open(os.environ["FAKE_REPAIR_STATE"], encoding="utf-8") as handle:
        status = handle.read()
    if not status:
        raise SystemExit(2)
    print(status)
elif sys.argv[1:2] == ["handle"]:
    output = os.environ["FAKE_HANDLE_OUTPUT"]
    if output == "exit-nonzero-unread":
        raise SystemExit(2)
    if output != "exit-zero-unread":
        sys.stdin.read()
        print(output)
"""


@dataclass(frozen=True, slots=True)
class ScriptedRepo:
    """Repair status and enforcer output the fake binary reports.

    An empty ``state`` makes the status command fail, and a ``None`` enrollment
    leaves the directory outside any managed repo.
    """

    state: str = REPAIR_REQUIRED
    handle: str = ENFORCER_ALLOW
    enrollment: str | None = ENABLED


def run_scripted_plugin(
    tmp_path: Path, statements: str, repo: ScriptedRepo = ScriptedRepo()
) -> ObjectDict:
    """Run statements after plugin setup and return the JSON object they print."""
    if repo.enrollment is not None:
        (tmp_path / "slopgate.toml").write_text(repo.enrollment, encoding="utf-8")
    executable = tmp_path / "slopgate"
    executable.write_text(_SCRIPTED_SLOPGATE, encoding="utf-8")
    executable.chmod(0o755)
    state_path = tmp_path / "repair-state.json"
    state_path.write_text(repo.state, encoding="utf-8")
    plugin_path = tmp_path / "slopgate-plugin.ts"
    plugin_path.write_text(
        render_opencode_plugin(
            resource_path("opencode_plugin.ts").read_text(encoding="utf-8"),
            str(executable),
            {"opencode_version": "2.2.5"},
        ),
        encoding="utf-8",
    )
    runner = tmp_path / "runner.ts"
    runner.write_text(
        v2_plugin_setup_source(plugin_path, tmp_path) + statements, encoding="utf-8"
    )
    link_v2_dependencies(tmp_path)
    completed = subprocess.run(
        ["bun", "run", str(runner)],
        cwd=tmp_path,
        env=os.environ
        | {
            "SLOPGATE_BIN": str(executable),
            "FAKE_REPAIR_STATE": str(state_path),
            "FAKE_HANDLE_OUTPUT": repo.handle,
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return object_dict(json.loads(completed.stdout))


def link_v2_dependencies(directory: Path) -> None:
    """Expose the pinned root OpenCode dependency to a temporary runner."""
    target = directory / "node_modules"
    if not target.exists():
        target.symlink_to(_REPOSITORY_NODE_MODULES, target_is_directory=True)


def v2_plugin_setup_source(
    plugin_path: Path,
    directory: Path,
    events: Sequence[Mapping[str, object]] | None = None,
    project_directory: Path | None = None,
) -> str:
    """Return TypeScript that loads a v2 plugin and captures domain callbacks."""
    return (
        _v2_plugin_preamble(plugin_path, directory, events, project_directory)
        + _v2_plugin_context()
    )


def _v2_plugin_preamble(
    plugin_path: Path,
    directory: Path,
    events: Sequence[Mapping[str, object]] | None,
    project_directory: Path | None,
) -> str:
    plugin_uri = json.dumps(plugin_path.as_uri())
    directory_literal = json.dumps(str(directory))
    project_literal = json.dumps(str(project_directory or directory))
    events_literal = json.dumps(events or [])
    return f"""
import plugin from {plugin_uri}

const __slopgateLogs = []
for (const level of [\"info\", \"warn\", \"error\"]) {{
  console[level] = (...args) => {{
    __slopgateLogs.push(args.map((arg) => typeof arg === \"string\" ? arg : JSON.stringify(arg)).join(\" \"))
  }}
}}
const __slopgateHooks = {{}}
const __slopgatePermissionHooks = {{}}
const __slopgateTools = {{}}
const __slopgateEvents = {events_literal}
const __slopgateEventState = {{ aborted: false }}
const __slopgateDirectory = {directory_literal}
const __slopgateProjectDirectory = {project_literal}
const __slopgateEditor = {{
  add(tool) {{
    __slopgateTools[tool.name] = tool
  }},
}}
"""


def _v2_plugin_context() -> str:
    return """
const __slopgateEventStream = (signal) => ({
  async *[Symbol.asyncIterator]() {
    signal?.addEventListener("abort", () => {
      __slopgateEventState.aborted = true
    })
    for (const event of __slopgateEvents) {
      if (signal?.aborted) return
      yield event
    }
  },
})
const __slopgateContext = {
  app: { name: "opencode", version: "2.2.5", channel: "stable" },
  location: {
    directory: __slopgateDirectory,
    project: {
      id: "project",
      directory: __slopgateProjectDirectory,
      canonical: __slopgateProjectDirectory,
    },
  },
  options: {},
  session: {
    get: async ({ sessionID }) => ({
      id: sessionID,
      location: { directory: __slopgateDirectory },
    }),
  },
  tool: {
    hook: async (name, callback) => {
      __slopgateHooks[name] = callback
    },
    transform: async (callback) => callback(__slopgateEditor),
  },
  permission: {
    hook: async (name, callback) => {
      __slopgatePermissionHooks[name] = callback
    },
  },
  event: {
    subscribe: (options) => __slopgateEventStream(options?.signal),
  },
}
const __slopgateCleanup = await plugin.setup(__slopgateContext)
"""


def v2_before_input(
    tool_name: str,
    session_id: str,
    args: object,
    call_id: str = "call",
) -> str:
    """Return a V2 execute.before callback invocation."""
    return f"""await __slopgateHooks[\"execute.before\"]({{
  tool: {json.dumps(tool_name)},
  sessionID: {json.dumps(session_id)},
  agent: \"build\",
  messageID: \"message\",
  id: {json.dumps(call_id)},
  input: {json.dumps(args)},
}})
"""


def v2_after_input(tool_name: str, session_id: str, args: object) -> str:
    """Return a V2 completed execute.after callback invocation."""
    return f"""await __slopgateHooks[\"execute.after\"]({{
  tool: {json.dumps(tool_name)},
  sessionID: {json.dumps(session_id)},
  agent: \"build\",
  messageID: \"message\",
  id: \"call\",
  input: {json.dumps(args)},
  status: \"completed\",
  result: {{ content: \"completed\", metadata: {{}} }},
}})
"""


def v2_after_error_input(tool_name: str, session_id: str, args: object) -> str:
    """Return a V2 failed execute.after callback invocation."""
    return f"""await __slopgateHooks[\"execute.after\"]({{
  tool: {json.dumps(tool_name)},
  sessionID: {json.dumps(session_id)},
  agent: \"build\",
  messageID: \"message\",
  id: \"call\",
  input: {json.dumps(args)},
  status: \"error\",
  error: {{ message: \"failed\" }},
}})
"""
