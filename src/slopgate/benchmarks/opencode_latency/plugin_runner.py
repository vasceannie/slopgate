"""Generated-plugin execution for the OpenCode latency benchmark."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from slopgate._types import ObjectDict, object_dict, object_list
from .models import (
    BenchmarkConfig,
    BenchmarkExecutionError,
    BenchmarkRun,
)
from slopgate.installer._opencode import render_opencode_plugin
from slopgate.resources import resource_path
from slopgate.util.platform import child_creation_flags


def _runner_source(plugin: Path, config: BenchmarkConfig) -> str:
    relative = config.target.relative_to(config.repo).as_posix()
    patch_text = f"*** Begin Patch\n*** Update File: {relative}\n*** End Patch\n"
    total = config.warmup + config.iterations
    return _runner_setup_source(plugin, config) + _runner_loop_source(patch_text, total)


def _runner_setup_source(plugin: Path, config: BenchmarkConfig) -> str:
    return f"""
import plugin from {json.dumps(plugin.as_uri())}
const __hooks = {{}}
const __tools = {{}}
const __directory = {json.dumps(str(config.repo))}
const __editor = {{
  add(tool) {{
    __tools[tool.name] = tool
  }},
}}
const __eventStream = (signal) => ({{
  async *[Symbol.asyncIterator]() {{
    if (signal?.aborted) return
  }},
}})
const __context = {{
  app: {{ name: "opencode", version: "2.2.5", channel: "stable" }},
  location: {{
    directory: __directory,
    project: {{ id: "project", directory: __directory, canonical: __directory }},
  }},
  options: {{}},
  session: {{
    get: async ({{ sessionID }}) => ({{
      id: sessionID,
      location: {{ directory: __directory }},
    }}),
  }},
  tool: {{
    hook: async (name, callback) => {{
      __hooks[name] = callback
    }},
    transform: async (callback) => callback(__editor),
  }},
  permission: {{
    hook: async () => {{}},
  }},
  event: {{
    subscribe: (options) => __eventStream(options?.signal),
  }},
}}
console.info = () => {{}}
console.warn = () => {{}}
console.error = () => {{}}
const __cleanup = await plugin.setup(__context)
"""


def _runner_loop_source(patch_text: str, total: int) -> str:
    return f"""
const totals = []
const outcomes = []
for (let index = 0; index < {total}; index += 1) {{
  const started = performance.now()
  try {{
    await __hooks["execute.after"]({{
      tool: "patch",
      sessionID: `slopgate-latency-benchmark-${{index}}`,
      agent: "build",
      messageID: "message",
      id: `benchmark-${{index}}`,
      input: {{ patchText: {json.dumps(patch_text)} }},
      status: "completed",
      result: {{ content: "completed", metadata: {{}} }},
    }})
    outcomes.push("returned")
  }} catch (error) {{
    outcomes.push(`blocked:${{String(error)}}`)
  }}
  totals.push(performance.now() - started)
}}
if (__cleanup) await __cleanup()
console.log(JSON.stringify({{ totals, outcomes }}))
"""


def _trace_rows(path: Path, warmup: int) -> list[ObjectDict]:
    rows: list[ObjectDict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        row = object_dict(json.loads(line))
        call_id = row.get("call_id")
        if isinstance(call_id, str) and call_id.startswith("benchmark-"):
            index = int(call_id.removeprefix("benchmark-"))
            if index >= warmup:
                rows.append(row)
    return rows


def _benchmark_environment(
    root: Path, config_path: Path, trace_root: Path
) -> dict[str, str]:
    return os.environ | {
        "SLOPGATE_CONFIG": str(config_path),
        "SLOPGATE_CONFIG_DIR": str(trace_root),
        "SLOPGATE_DAEMON_SOCKET": str(root / "direct-engine.sock"),
        "SLOPGATE_ROOT": str(trace_root),
    }


def _prepare_benchmark_run(
    root: Path, config: BenchmarkConfig, identity: ObjectDict
) -> tuple[Path, Path, Path]:
    (root / "node_modules").symlink_to(
        Path(__file__).parents[4] / "node_modules",
        target_is_directory=True,
    )
    trace_root = root / "trace"
    config_path = root / "config.json"
    config_path.write_text(
        json.dumps({"trace_dir": str(trace_root / "logs")}), encoding="utf-8"
    )
    plugin = root / "slopgate-plugin.ts"
    plugin.write_text(
        render_opencode_plugin(
            resource_path("opencode_plugin.ts").read_text(encoding="utf-8"),
            config.binary,
            identity,
        ),
        encoding="utf-8",
    )
    runner = root / "runner.ts"
    runner.write_text(_runner_source(plugin, config), encoding="utf-8")
    return runner, trace_root, config_path


def _collect_benchmark_run(
    completed: subprocess.CompletedProcess[str],
    trace_root: Path,
    config: BenchmarkConfig,
) -> BenchmarkRun:
    result = object_dict(json.loads(completed.stdout))
    totals = [
        float(item)
        for item in object_list(result.get("totals"))
        if isinstance(item, int | float)
    ][config.warmup :]
    outcomes = [
        item for item in object_list(result.get("outcomes")) if isinstance(item, str)
    ][config.warmup :]
    trace_path = trace_root / "logs" / "results.jsonl"
    if not trace_path.is_file():
        message = (
            "benchmark subprocess produced no result trace; "
            f"outcomes={outcomes!r}; stderr={completed.stderr.strip()!r}"
        )
        raise BenchmarkExecutionError(message)
    return BenchmarkRun(totals, outcomes, _trace_rows(trace_path, config.warmup))


def run_plugin(config: BenchmarkConfig, identity: ObjectDict) -> BenchmarkRun:
    """Drive the awaited plugin hook and collect its isolated result traces."""
    with TemporaryDirectory(prefix="slopgate-opencode-benchmark-") as directory:
        root = Path(directory)
        runner, trace_root, config_path = _prepare_benchmark_run(root, config, identity)
        completed = subprocess.run(
            ["bun", "run", str(runner)],
            cwd=config.repo,
            env=_benchmark_environment(root, config_path, trace_root),
            text=True,
            capture_output=True,
            check=False,
            creationflags=child_creation_flags(),
        )
        if completed.returncode != 0:
            raise BenchmarkExecutionError(completed.stderr.strip())
        return _collect_benchmark_run(completed, trace_root, config)
