from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from slopgate.installer._opencode import render_opencode_plugin
from slopgate.resources import resource_path


pytestmark = pytest.mark.skipif(shutil.which("bun") is None, reason="Bun is required")

_UNCLASSIFIED_TOOL_CASES = [
    pytest.param(
        "custom_write",
        {"filename": "sample.py", "content": "x"},
        id="filename-mutator",
    ),
    pytest.param(
        "custom_write",
        {"paths": ["sample.py"], "content": "x"},
        id="paths-mutator",
    ),
    pytest.param(
        "custom_write",
        {"uri": "file:///tmp/sample.py", "content": "x"},
        id="file-uri-mutator",
    ),
    pytest.param(
        "custom_write",
        {"input": {"path": "sample.py", "content": "x"}},
        id="nested-mutator",
    ),
    pytest.param(
        "interactive_bash",
        {"tmux_command": "send-keys -t dev 'touch sample.py' Enter"},
        id="interactive-shell-wrapper",
    ),
    pytest.param(
        "skill_mcp",
        {
            "mcp_name": "fs",
            "tool_name": "write_file",
            "arguments": {"path": "sample.py", "content": "x"},
        },
        id="mcp-dispatch-wrapper",
    ),
]
_REMOTE_EFFECT_TOOL_CASES = [
    pytest.param(
        "github_update_issue",
        {"path": "/repos/o/r/issues/1", "body": "fixed"},
        id="github-api-resource-path",
    ),
    pytest.param(
        "api_delete_resource",
        {"path": "/v1/items/1"},
        id="declared-api-resource-path",
    ),
]


def _run_plugin_with_real_slopgate(
    tmp_path: Path,
    tool_name: str,
    tool_args: dict[str, object],
) -> subprocess.CompletedProcess[str]:
    (tmp_path / "slopgate.toml").write_text(
        "[slopgate]\nenabled = true\n", encoding="utf-8"
    )
    plugin_path = tmp_path / "slopgate-plugin.ts"
    plugin_path.write_text(
        render_opencode_plugin(
            resource_path("opencode_plugin.ts").read_text(encoding="utf-8"),
            sys.executable,
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
  {{ args: {json.dumps(tool_args)} }},
)
console.log("allowed")
""",
        encoding="utf-8",
    )
    env = dict(os.environ)
    env.pop("SLOPGATE_BIN", None)
    env["SLOPGATE_DAEMON_SOCKET"] = str(tmp_path / "no-daemon.sock")
    env["SLOPGATE_ROOT"] = str(tmp_path / "slopgate-root")
    return subprocess.run(
        ["bun", "run", str(runner)],
        cwd=tmp_path,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_generated_plugin_blocks_invalid_mutating_projection(tmp_path: Path) -> None:
    result = _run_plugin_with_real_slopgate(
        tmp_path, "apply_patch", {"patchText": "not a patch"}
    )
    assert result.returncode != 0, "unresolved mutating projections must not execute"
    assert "invalid" in result.stderr, "the plugin must surface the engine denial"


def test_generated_plugin_allows_known_read_only_tool(tmp_path: Path) -> None:
    result = _run_plugin_with_real_slopgate(tmp_path, "read", {"filePath": "sample.py"})
    assert result.returncode == 0, result.stderr
    assert "allowed" in result.stdout


def test_generated_plugin_allows_unprojected_read_only_mcp_tool(tmp_path: Path) -> None:
    result = _run_plugin_with_real_slopgate(
        tmp_path, "gitnexus_context", {"name": "sample"}
    )
    assert result.returncode == 0, result.stderr
    assert "allowed" in result.stdout


def test_generated_plugin_allows_task_delegation(tmp_path: Path) -> None:
    result = _run_plugin_with_real_slopgate(
        tmp_path, "task", {"category": "quick", "prompt": "edit sample.py"}
    )
    assert result.returncode == 0, result.stderr
    assert "allowed" in result.stdout


@pytest.mark.parametrize(("tool_name", "tool_args"), _UNCLASSIFIED_TOOL_CASES)
def test_generated_plugin_allows_unclassified_tools_in_clean_state(
    tmp_path: Path,
    tool_name: str,
    tool_args: dict[str, object],
) -> None:
    result = _run_plugin_with_real_slopgate(tmp_path, tool_name, tool_args)

    assert result.returncode == 0, result.stderr
    assert "allowed" in result.stdout


@pytest.mark.parametrize(("tool_name", "tool_args"), _REMOTE_EFFECT_TOOL_CASES)
def test_generated_plugin_allows_declared_remote_effects_in_clean_state(
    tmp_path: Path,
    tool_name: str,
    tool_args: dict[str, object],
) -> None:
    result = _run_plugin_with_real_slopgate(tmp_path, tool_name, tool_args)

    assert result.returncode == 0, result.stderr
    assert "allowed" in result.stdout
