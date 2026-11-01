from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path

_REPOSITORY_NODE_MODULES = Path(__file__).parents[2] / "node_modules"


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
