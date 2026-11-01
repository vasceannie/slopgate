from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from slopgate._types import object_dict, object_list
from slopgate.installer._opencode import render_opencode_plugin
from slopgate.resources import resource_path
from tests.integration.opencode_plugin_v2_support import (
    link_v2_dependencies,
    v2_before_input,
    v2_plugin_setup_source,
)


pytestmark = pytest.mark.skipif(shutil.which("bun") is None, reason="Bun is required")


@dataclass(frozen=True, slots=True)
class _PendingRepairRepo:
    status_available: bool = True
    enabled: bool = True
    commented_header: bool = False


def _write_fake_slopgate(tmp_path: Path, repo: _PendingRepairRepo) -> Path:
    header = "[slopgate] # managed by test" if repo.commented_header else "[slopgate]"
    (tmp_path / "slopgate.toml").write_text(
        f"{header}\nenabled = {'true' if repo.enabled else 'false'}\n", encoding="utf-8"
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
    sys.stdin.read()
    print(json.dumps({"action": "allow"}))
""",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable


def _write_runner(tmp_path: Path, executable: Path, statements: str) -> Path:
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
    return runner


def _run_pending_repair_file_tool(
    tmp_path: Path,
    tool_name: str,
    repo: _PendingRepairRepo = _PendingRepairRepo(),
) -> subprocess.CompletedProcess[str]:
    executable = _write_fake_slopgate(tmp_path, repo)
    runner = _write_runner(
        tmp_path,
        executable,
        v2_before_input(
            tool_name,
            "session",
            {"patchText": "*** Begin Patch\\n*** End Patch"},
        )
        + 'console.log("allowed")\n',
    )
    return subprocess.run(
        ["bun", "run", str(runner)],
        cwd=tmp_path,
        env=os.environ
        | {
            "SLOPGATE_BIN": str(executable),
            "REPAIR_STATUS_AVAILABLE": "1" if repo.status_available else "0",
        },
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.mark.parametrize("tool_name", ("patch", "edit", "write"))
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
        tmp_path, "patch", _PendingRepairRepo(status_available=False)
    )

    assert result.returncode == 0, result.stderr


def test_opencode_toml_header_comments_preserve_relaxed_repo_mode(
    tmp_path: Path,
) -> None:
    result = _run_pending_repair_file_tool(
        tmp_path,
        "unknown_tool",
        _PendingRepairRepo(enabled=False, commented_header=True),
    )

    assert result.returncode == 0, result.stderr
    assert "allowed" in result.stdout


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
    state_path = Path(os.environ["REPAIR_STATE_PATH"])
    if state_path.exists():
        print(state_path.read_text(encoding="utf-8"))
    else:
        print(json.dumps({"status": "clean"}))
elif sys.argv[1:3] == ["repair", "verify"]:
    started.write_text(str(int(started.read_text() or "0") + 1), encoding="utf-8")
    time.sleep(float(os.environ.get("VERIFY_SLEEP_SECONDS", "8")))
    Path(os.environ["REPAIR_STATE_PATH"]).unlink(missing_ok=True)
    print(json.dumps({"status": "cleared", "generation": "generation-1"}))
else:
    sys.stdin.read()
    print(json.dumps({"action": "allow"}))
""",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable


def _verify_statements(*, concurrent: bool, abort_first: bool) -> str:
    return f"""
const tool = __slopgateTools["slopgate_verify_repair"]
const firstController = new AbortController()
const secondController = new AbortController()
const firstContext = {{
  sessionID: "session",
  agent: "build",
  messageID: "message",
  id: "verify-call",
  signal: firstController.signal,
}}
const secondContext = {{
  sessionID: "session",
  agent: "build",
  messageID: "message",
  id: "verify-call-2",
  signal: secondController.signal,
}}
const first = tool.execute({{}}, firstContext)
const second = {json.dumps(concurrent)}
  ? tool.execute({{}}, secondContext)
  : Promise.resolve(null)
if ({json.dumps(abort_first)}) setTimeout(() => firstController.abort(), 50)
const results = await Promise.allSettled([first, second])
console.log(JSON.stringify(results.map((item) => {{
  if (item.status === "fulfilled") return item.value
  return {{ error: String(item.reason) }}
}})))
"""


def _run_verify_repair(
    tmp_path: Path,
    *,
    timeout_ms: int,
    concurrent: bool,
    abort_first: bool = False,
) -> subprocess.CompletedProcess[str]:
    executable = _write_timeout_slopgate(tmp_path)
    started = tmp_path / "verify-started.txt"
    started.write_text("0", encoding="utf-8")
    state = tmp_path / "repair-state.json"
    state.write_text(
        json.dumps({"status": "REPAIR_REQUIRED", "generation": "generation-1"}),
        encoding="utf-8",
    )
    runner = _write_runner(
        tmp_path,
        executable,
        _verify_statements(concurrent=concurrent, abort_first=abort_first),
    )
    return subprocess.run(
        ["bun", "run", str(runner)],
        cwd=tmp_path,
        env=os.environ
        | {
            "SLOPGATE_BIN": str(executable),
            "SLOPGATE_REPAIR_VERIFY_TIMEOUT_MS": str(timeout_ms),
            "VERIFY_STARTED_PATH": str(started),
            "REPAIR_STATE_PATH": str(state),
            "VERIFY_SLEEP_SECONDS": "1",
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
    state = json.loads((tmp_path / "repair-state.json").read_text(encoding="utf-8"))
    assert state == {"status": "REPAIR_REQUIRED", "generation": "generation-1"}


def test_verify_repair_joins_inflight_generation_instead_of_second_scan(
    tmp_path: Path,
) -> None:
    result = _run_verify_repair(tmp_path, timeout_ms=2000, concurrent=True)
    started = (tmp_path / "verify-started.txt").read_text(encoding="utf-8")

    assert result.returncode == 0, result.stderr
    assert started.strip() == "1", (
        "stacked verify calls for one generation must join the in-flight scan"
    )


def test_verify_repair_first_caller_abort_does_not_cancel_shared_flight(
    tmp_path: Path,
) -> None:
    result = _run_verify_repair(
        tmp_path,
        timeout_ms=3000,
        concurrent=True,
        abort_first=True,
    )

    assert result.returncode == 0, result.stderr
    results = object_list(json.loads(result.stdout))
    assert all(
        isinstance(item, dict)
        and "cleared" in str(object_dict(item).get("content", ""))
        for item in results
    )
    assert not (tmp_path / "repair-state.json").exists()
