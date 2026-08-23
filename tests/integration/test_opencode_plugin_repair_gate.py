from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from slopgate.installer._opencode import render_opencode_plugin
from slopgate.resources import resource_path


pytestmark = pytest.mark.skipif(shutil.which("bun") is None, reason="Bun is required")


def _write_fake_slopgate(tmp_path: Path) -> Path:
    (tmp_path / "slopgate.toml").write_text(
        "[slopgate]\nenabled = true\n", encoding="utf-8"
    )
    executable = tmp_path / "slopgate"
    executable.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys

if sys.argv[1:3] == ["repair", "status"]:
    if os.environ.get("REPAIR_STATUS_AVAILABLE") == "0":
        raise SystemExit(2)
    print(json.dumps({"status": "REPAIR_REQUIRED", "generation": "generation-1"}))
else:
    print(json.dumps({"action": "allow"}))
""",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable


def _run_pending_repair_file_tool(
    tmp_path: Path, tool_name: str, status_available: bool = True
) -> subprocess.CompletedProcess[str]:
    executable = _write_fake_slopgate(tmp_path)
    plugin_path = tmp_path / "slopgate-plugin.ts"
    plugin_path.write_text(
        render_opencode_plugin(
            resource_path("opencode_plugin.ts").read_text(encoding="utf-8"),
            str(executable),
            {"opencode_version": "1.18.21"},
        ),
        encoding="utf-8",
    )
    runner = tmp_path / "runner.ts"
    runner.write_text(
        f"""
import {{ EnforcerPlugin }} from {json.dumps(plugin_path.as_uri())}

const handlers = await EnforcerPlugin({{
  client: {{ app: {{ log: async () => {{}} }} }},
  directory: {json.dumps(str(tmp_path))},
  worktree: {json.dumps(str(tmp_path))},
}})
await handlers["tool.execute.before"](
  {{ tool: {json.dumps(tool_name)}, sessionID: "session", callID: "call" }},
  {{ args: {{ patchText: "*** Begin Patch\\n*** End Patch" }} }},
)
console.log("allowed")
""",
        encoding="utf-8",
    )
    return subprocess.run(
        ["bun", "run", str(runner)],
        cwd=tmp_path,
        env=os.environ
        | {
            "SLOPGATE_BIN": str(executable),
            "REPAIR_STATUS_AVAILABLE": "1" if status_available else "0",
        },
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.mark.parametrize("tool_name", ("apply_patch", "edit", "write"))
def test_pending_repair_allows_direct_file_repair_tool(
    tmp_path: Path, tool_name: str
) -> None:
    result = _run_pending_repair_file_tool(tmp_path, tool_name)

    assert result.returncode == 0, result.stderr
    assert "allowed" in result.stdout


def test_pending_repair_allows_bootstrap_when_status_is_unavailable(
    tmp_path: Path,
) -> None:
    result = _run_pending_repair_file_tool(
        tmp_path, "apply_patch", status_available=False
    )

    assert result.returncode == 0, result.stderr


def _write_timeout_slopgate(tmp_path: Path) -> Path:
    (tmp_path / "slopgate.toml").write_text(
        "[slopgate]\nenabled = true\n", encoding="utf-8"
    )
    executable = tmp_path / "slopgate"
    executable.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys
import time
from pathlib import Path

started = Path(os.environ["VERIFY_STARTED_PATH"])
if sys.argv[1:3] == ["repair", "status"]:
    print(json.dumps({"status": "REPAIR_REQUIRED", "generation": "generation-1"}))
elif sys.argv[1:3] == ["repair", "verify"]:
    started.write_text(str(int(started.read_text() or "0") + 1), encoding="utf-8")
    time.sleep(8)
    print(json.dumps({"status": "cleared", "generation": "generation-1"}))
else:
    print(json.dumps({"action": "allow"}))
""",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable


def _run_verify_repair(
    tmp_path: Path, *, timeout_ms: int, concurrent: bool
) -> subprocess.CompletedProcess[str]:
    executable = _write_timeout_slopgate(tmp_path)
    started = tmp_path / "verify-started.txt"
    started.write_text("0", encoding="utf-8")
    plugin_path = tmp_path / "slopgate-plugin.ts"
    plugin_path.write_text(
        render_opencode_plugin(
            resource_path("opencode_plugin.ts").read_text(encoding="utf-8"),
            str(executable),
            {"opencode_version": "1.18.21"},
        ),
        encoding="utf-8",
    )
    runner = tmp_path / "runner.ts"
    runner.write_text(
        f"""
import {{ EnforcerPlugin }} from {json.dumps(plugin_path.as_uri())}

const handlers = await EnforcerPlugin({{
  client: {{ app: {{ log: async () => {{}} }} }},
  directory: {json.dumps(str(tmp_path))},
  worktree: {json.dumps(str(tmp_path))},
}})
const tool = handlers.tool.slopgate_verify_repair
const first = tool.execute({{}})
const second = {json.dumps(concurrent)} ? tool.execute({{}}) : Promise.resolve(null)
const results = await Promise.allSettled([first, second])
console.log(JSON.stringify(results.map((item) => {{
  if (item.status === "fulfilled") return item.value
  return String(item.reason)
}})))
""",
        encoding="utf-8",
    )
    return subprocess.run(
        ["bun", "run", str(runner)],
        cwd=tmp_path,
        env=os.environ
        | {
            "SLOPGATE_BIN": str(executable),
            "SLOPGATE_REPAIR_VERIFY_TIMEOUT_MS": str(timeout_ms),
            "VERIFY_STARTED_PATH": str(started),
        },
        text=True,
        capture_output=True,
        check=False,
    )


def test_verify_repair_timeout_returns_structured_failure_and_retains(
    tmp_path: Path,
) -> None:
    result = _run_verify_repair(tmp_path, timeout_ms=400, concurrent=False)

    assert result.returncode == 0, result.stderr
    assert "timeout" in result.stdout, (
        "plugin timeout must return structured timeout JSON, not wedge"
    )


def test_verify_repair_joins_inflight_generation_instead_of_second_scan(
    tmp_path: Path,
) -> None:
    result = _run_verify_repair(tmp_path, timeout_ms=2000, concurrent=True)
    started = (tmp_path / "verify-started.txt").read_text(encoding="utf-8")

    assert result.returncode == 0, result.stderr
    assert started.strip() == "1", (
        "stacked verify calls for one generation must join the in-flight scan"
    )
