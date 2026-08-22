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


def _runner_source(plugin: Path, config: BenchmarkConfig) -> str:
    relative = config.target.relative_to(config.repo).as_posix()
    total = config.warmup + config.iterations
    return f"""
import {{ EnforcerPlugin }} from {json.dumps(plugin.as_uri())}
const handlers = await EnforcerPlugin({{
  client: {{ app: {{ log: async () => undefined }} }},
  directory: {json.dumps(str(config.repo))},
  worktree: {json.dumps(str(config.repo))},
}})
const totals = []
const outcomes = []
for (let index = 0; index < {total}; index += 1) {{
  const started = performance.now()
  try {{
    await handlers["tool.execute.after"](
      {{
        tool: "apply_patch",
        sessionID: `slopgate-latency-benchmark-${{index}}`,
        callID: `benchmark-${{index}}`,
        args: {{ filePath: {json.dumps(relative)} }},
      }},
      {{ title: "benchmark", metadata: {{ benchmark: true }}, output: "applied" }},
    )
    outcomes.push("returned")
  }} catch (error) {{
    outcomes.push(`blocked:${{String(error)}}`)
  }}
  totals.push(performance.now() - started)
}}
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


def _benchmark_environment(root: Path, config_path: Path, trace_root: Path) -> dict[str, str]:
    return os.environ | {
        "SLOPGATE_CONFIG": str(config_path),
        "SLOPGATE_CONFIG_DIR": str(trace_root),
        "SLOPGATE_DAEMON_SOCKET": str(root / "direct-engine.sock"),
        "SLOPGATE_ROOT": str(trace_root),
    }


def run_plugin(config: BenchmarkConfig, identity: ObjectDict) -> BenchmarkRun:
    """Drive the awaited plugin hook and collect its isolated result traces."""
    with TemporaryDirectory(prefix="slopgate-opencode-benchmark-") as directory:
        root = Path(directory)
        plugin = root / "slopgate-plugin.ts"
        runner = root / "runner.ts"
        trace_root = root / "trace"
        config_path = root / "config.json"
        config_path.write_text(
            json.dumps({"trace_dir": str(trace_root / "logs")}), encoding="utf-8"
        )
        plugin.write_text(
            render_opencode_plugin(
                resource_path("opencode_plugin.ts").read_text(encoding="utf-8"),
                config.binary,
                identity,
            ),
            encoding="utf-8",
        )
        runner.write_text(_runner_source(plugin, config), encoding="utf-8")
        completed = subprocess.run(
            ["bun", "run", str(runner)],
            cwd=config.repo,
            env=_benchmark_environment(root, config_path, trace_root),
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            raise BenchmarkExecutionError(completed.stderr.strip())
        result = object_dict(json.loads(completed.stdout))
        totals = [
            float(item)
            for item in object_list(result.get("totals"))
            if isinstance(item, int | float)
        ][config.warmup :]
        outcomes = [
            item
            for item in object_list(result.get("outcomes"))
            if isinstance(item, str)
        ][config.warmup :]
        trace_path = trace_root / "logs" / "results.jsonl"
        if not trace_path.is_file():
            message = (
                "benchmark subprocess produced no result trace; "
                f"outcomes={outcomes!r}; stderr={completed.stderr.strip()!r}"
            )
            raise BenchmarkExecutionError(message)
        return BenchmarkRun(totals, outcomes, _trace_rows(trace_path, config.warmup))
