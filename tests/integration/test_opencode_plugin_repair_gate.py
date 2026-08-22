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
import sys

if sys.argv[1:3] == ["repair", "status"]:
    print(json.dumps({"status": "REPAIR_REQUIRED", "generation": "generation-1"}))
else:
    print(json.dumps({"action": "allow"}))
""",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable


def _run_pending_repair_file_tool(tmp_path: Path) -> subprocess.CompletedProcess[str]:
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
  {{ tool: "apply_patch", sessionID: "session", callID: "call" }},
  {{ args: {{ patchText: "*** Begin Patch\\n*** End Patch" }} }},
)
console.log("allowed")
""",
        encoding="utf-8",
    )
    return subprocess.run(
        ["bun", "run", str(runner)],
        cwd=tmp_path,
        env=os.environ | {"SLOPGATE_BIN": str(executable)},
        text=True,
        capture_output=True,
        check=False,
    )


def test_pending_repair_allows_direct_file_repair_tool(tmp_path: Path) -> None:
    result = _run_pending_repair_file_tool(tmp_path)

    assert result.returncode == 0, result.stderr
    assert "allowed" in result.stdout
