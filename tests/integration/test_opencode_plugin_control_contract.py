from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from slopgate._types import object_dict
from slopgate.installer._opencode import render_opencode_plugin
from slopgate.resources import resource_path


pytestmark = pytest.mark.skipif(shutil.which("bun") is None, reason="Bun is required")
_DEFAULT_TOOL_ARGS: dict[str, object] = {
    "filePath": "sample.py",
    "content": "print('ok')\n",
}
_TOOL_ARGS_BY_MODE: dict[str, dict[str, object]] = {
    "repair-required-command-safe": {"command": "slopgate lint check --details"},
    "repair-required-command-compound": {
        "command": "slopgate lint check && touch bypassed"
    },
    "repair-required-wrapper-interactive": {
        "tmux_command": "send-keys -t dev 'touch sample.py' Enter"
    },
    "repair-required-wrapper-skill-mcp": {
        "mcp_name": "fs",
        "tool_name": "write_file",
        "arguments": {"path": "sample.py", "content": "x"},
    },
    "repair-required-wrapper-task": {
        "category": "quick",
        "prompt": "edit sample.py",
    },
}
_TOOL_NAME_BY_MODE = {
    "repair-required": "custom_mutator",
    "unknown-effect": "custom_mutator",
    "unknown-readonly": "gitnexus_context",
    "repair-required-read": "read",
    "repair-required-read-gitnexus": "gitnexus_context",
    "repair-required-read-skill": "skill",
    "repair-required-wrapper-interactive": "interactive_bash",
    "repair-required-wrapper-skill-mcp": "skill_mcp",
    "repair-required-wrapper-task": "task",
}
_FAIL_CLOSED_TOOL_CASES = [
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
    pytest.param(
        "task",
        {"category": "quick", "prompt": "edit sample.py"},
        id="task-delegation-wrapper",
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

mode = os.environ.get("CONTRACT_RESPONSE_MODE", "block")
if sys.argv[1:3] == ["repair", "status"]:
    if mode == "repair-unavailable":
        print("repair state unavailable", file=sys.stderr)
        raise SystemExit(2)
    status = "REPAIR_REQUIRED" if mode.startswith("repair-required") else "CLEAN"
    print(json.dumps({"status": status, "generation": "generation-1"}))
else:
    payload = json.load(sys.stdin)
    if mode == "mutate":
        print(json.dumps({"action": "allow", "updated_args": {"content": "mutated"}}))
    elif mode.startswith("repair-required-command"):
        print(json.dumps({"action": "allow"}))
    elif mode == "unknown-readonly":
        print(json.dumps({"action": "allow"}))
    elif mode.startswith("repair-required-read"):
        pass
    else:
        version = payload.get("opencode_tool_contract_version", "missing")
        print(json.dumps({"action": "block", "reason": f"contract block version={version}"}))
""",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable


def _run_plugin_contract(
    tmp_path: Path,
    native_event: str,
    response_mode: str = "block",
) -> subprocess.CompletedProcess[str]:
    runner = tmp_path / "runner.ts"
    executable = _write_fake_slopgate(tmp_path)
    selected_args = _TOOL_ARGS_BY_MODE.get(response_mode, _DEFAULT_TOOL_ARGS)
    tool_name = (
        "bash"
        if response_mode.startswith("repair-required-command")
        else _TOOL_NAME_BY_MODE.get(response_mode, "write")
    )
    plugin_path = tmp_path / "slopgate-plugin.ts"
    plugin_path.write_text(
        render_opencode_plugin(
            resource_path("opencode_plugin.ts").read_text(encoding="utf-8"),
            str(executable),
            {"opencode_version": "1.18.21"},
        ),
        encoding="utf-8",
    )
    runner.write_text(
        f"""
import {{ EnforcerPlugin }} from {json.dumps(plugin_path.as_uri())}

const logs: string[] = []
const handlers = await EnforcerPlugin({{
  client: {{ app: {{ log: async (entry) => {{ logs.push(entry.body.message) }} }} }},
  directory: {json.dumps(str(tmp_path))},
  worktree: {json.dumps(str(tmp_path))},
}})
const output = {{ args: {json.dumps(selected_args)} }}
let hookReturn: unknown

if ({json.dumps(native_event)} === "file.edited") {{
  await handlers.event({{ event: {{ type: "file.edited", properties: {{ file: "sample.py" }} }} }})
}} else {{
  hookReturn = await handlers["tool.execute.before"](
    {{ tool: {json.dumps(tool_name)}, sessionID: "session", callID: "call" }},
    output,
  )
}}
console.log(JSON.stringify({{ logs, hookReturn, args: output.args }}))
""",
        encoding="utf-8",
    )
    return subprocess.run(
        ["bun", "run", str(runner)],
        cwd=tmp_path,
        env=os.environ | {"SLOPGATE_BIN": str(executable), "CONTRACT_RESPONSE_MODE": response_mode},
        text=True,
        capture_output=True,
        check=False,
    )


def test_file_edited_block_is_logged_without_throwing(tmp_path: Path) -> None:
    result = _run_plugin_contract(tmp_path, "file.edited")

    assert result.returncode == 0, result.stderr
    assert "contract block" in result.stdout


def test_typed_before_hook_still_throws_for_block(tmp_path: Path) -> None:
    result = _run_plugin_contract(tmp_path, "tool.execute.before")

    assert result.returncode != 0
    assert "contract block" in result.stderr


def test_installed_plugin_forwards_tool_contract_version(tmp_path: Path) -> None:
    result = _run_plugin_contract(tmp_path, "tool.execute.before")

    assert result.returncode != 0
    assert "version=slopgate-opencode-projection-v1" in result.stderr


def test_pending_repair_blocks_unknown_effect_tool(tmp_path: Path) -> None:
    result = _run_plugin_contract(tmp_path, "tool.execute.before", "repair-required")

    assert result.returncode != 0
    assert "repair required for generation generation-1" in result.stderr


def test_pending_repair_allows_read_only_tool(tmp_path: Path) -> None:
    result = _run_plugin_contract(tmp_path, "tool.execute.before", "repair-required-read")

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "response_mode",
    [
        pytest.param("repair-required-read-gitnexus", id="gitnexus-context"),
        pytest.param("repair-required-read-skill", id="skill-loader"),
    ],
)
def test_pending_repair_allows_trusted_read_only_tool(
    tmp_path: Path,
    response_mode: str,
) -> None:
    result = _run_plugin_contract(tmp_path, "tool.execute.before", response_mode)

    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "response_mode",
    [
        pytest.param(
            "repair-required-wrapper-interactive",
            id="interactive-shell-wrapper",
        ),
        pytest.param("repair-required-wrapper-skill-mcp", id="mcp-dispatch-wrapper"),
        pytest.param("repair-required-wrapper-task", id="task-delegation-wrapper"),
    ],
)
def test_pending_repair_blocks_opaque_wrappers(
    tmp_path: Path,
    response_mode: str,
) -> None:
    result = _run_plugin_contract(tmp_path, "tool.execute.before", response_mode)

    assert result.returncode != 0, "opaque wrappers must not bypass pending repair"
    assert "repair required for generation generation-1" in result.stderr, (
        "the repair gate must reject wrappers before delegating to the engine"
    )


def test_pending_repair_allows_exact_lint_check_command(tmp_path: Path) -> None:
    result = _run_plugin_contract(
        tmp_path,
        "tool.execute.before",
        "repair-required-command-safe",
    )

    assert result.returncode == 0, result.stderr


def test_pending_repair_rejects_compound_lint_check_command(tmp_path: Path) -> None:
    result = _run_plugin_contract(
        tmp_path,
        "tool.execute.before",
        "repair-required-command-compound",
    )

    assert result.returncode != 0, "compound verification commands must remain blocked"
    assert "repair required for generation generation-1" in result.stderr, (
        "the repair gate should reject shell suffixes instead of executing them"
    )


def test_managed_repo_blocks_when_repair_state_is_unavailable(tmp_path: Path) -> None:
    result = _run_plugin_contract(
        tmp_path,
        "tool.execute.before",
        "repair-unavailable",
    )

    assert result.returncode != 0, "managed repositories must fail closed on unreadable state"
    assert "repair gate state is unavailable" in result.stderr, (
        "the plugin should explain why execution was denied"
    )


def test_typed_before_hook_mutates_output_args_in_place(tmp_path: Path) -> None:
    result = _run_plugin_contract(tmp_path, "tool.execute.before", "mutate")
    observation = object_dict(json.loads(result.stdout))
    args = object_dict(observation.get("args"))

    assert args.get("content") == "mutated", "updated args must reach the host object"


def test_typed_hook_return_value_is_ignored(tmp_path: Path) -> None:
    result = _run_plugin_contract(tmp_path, "tool.execute.before", "mutate")
    observation = object_dict(json.loads(result.stdout))

    assert "hookReturn" not in observation, "typed hook must resolve without a value"


def test_generated_plugin_denies_unknown_effect_tool(tmp_path: Path) -> None:
    result = _run_plugin_contract(tmp_path, "tool.execute.before", "unknown-effect")

    assert result.returncode != 0, "unknown custom tools must be denied by the plugin"
    assert "unknown OpenCode tool effect" in result.stderr


def test_generated_plugin_allows_unknown_read_only_tool(tmp_path: Path) -> None:
    result = _run_plugin_contract(tmp_path, "tool.execute.before", "unknown-readonly")

    assert result.returncode == 0, result.stderr


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


@pytest.mark.parametrize(("tool_name", "tool_args"), _FAIL_CLOSED_TOOL_CASES)
def test_generated_plugin_denies_unknown_mutations_and_wrappers(
    tmp_path: Path,
    tool_name: str,
    tool_args: dict[str, object],
) -> None:
    result = _run_plugin_with_real_slopgate(tmp_path, tool_name, tool_args)

    assert result.returncode != 0, "unknown mutations and wrappers must fail closed"
    assert "unknown OpenCode tool effect" in result.stderr


@pytest.mark.parametrize(("tool_name", "tool_args"), _REMOTE_EFFECT_TOOL_CASES)
def test_generated_plugin_allows_declared_remote_effects_in_clean_state(
    tmp_path: Path,
    tool_name: str,
    tool_args: dict[str, object],
) -> None:
    result = _run_plugin_with_real_slopgate(tmp_path, tool_name, tool_args)

    assert result.returncode == 0, result.stderr
    assert "allowed" in result.stdout
