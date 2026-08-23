from __future__ import annotations

import json
import os
import shutil
import subprocess
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
    "outside-unknown": "custom_mutator",
    "relaxed-unknown": "custom_mutator",
    "repair-required-read": "read",
    "repair-required-read-gitnexus": "gitnexus_context",
    "repair-required-read-skill": "skill",
    "repair-required-wrapper-interactive": "interactive_bash",
    "repair-required-wrapper-skill-mcp": "skill_mcp",
    "repair-required-wrapper-task": "task",
}
def _write_fake_slopgate(tmp_path: Path, repo_mode: str = "strict") -> Path:
    if repo_mode != "outside":
        enabled = "false" if repo_mode == "relaxed" else "true"
        (tmp_path / "slopgate.toml").write_text(
            f"[slopgate]\nenabled = {enabled}\n", encoding="utf-8"
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
    elif mode in {"outside-unknown", "relaxed-unknown"}:
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


def _write_plugin_runner(
    tmp_path: Path,
    plugin_path: Path,
    native_event: str,
    response_mode: str,
) -> Path:
    selected_args = _TOOL_ARGS_BY_MODE.get(response_mode, _DEFAULT_TOOL_ARGS)
    tool_name = (
        "bash"
        if response_mode.startswith("repair-required-command")
        else _TOOL_NAME_BY_MODE.get(response_mode, "write")
    )
    runner = tmp_path / "runner.ts"
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
}} else if ({json.dumps(native_event)} === "tool.execute.after") {{
  await handlers["tool.execute.after"](
    {{
      tool: {json.dumps(tool_name)},
      sessionID: "session",
      callID: "call",
      args: {json.dumps(selected_args)},
    }},
    {{ title: "sample", output: "completed", metadata: {{}} }},
  )
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
    return runner


def _run_plugin_contract(
    tmp_path: Path,
    native_event: str,
    response_mode: str = "block",
    repo_mode: str = "strict",
) -> subprocess.CompletedProcess[str]:
    executable = _write_fake_slopgate(tmp_path, repo_mode)
    plugin_path = tmp_path / "slopgate-plugin.ts"
    plugin_path.write_text(
        render_opencode_plugin(
            resource_path("opencode_plugin.ts").read_text(encoding="utf-8"),
            str(executable),
            {"opencode_version": "1.18.21"},
        ),
        encoding="utf-8",
    )
    runner = _write_plugin_runner(tmp_path, plugin_path, native_event, response_mode)
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


def test_typed_after_hook_logs_detection_without_claiming_prevention(
    tmp_path: Path,
) -> None:
    result = _run_plugin_contract(tmp_path, "tool.execute.after")
    expected_fragments = (
        "post-tool detection only",
        "no prevention or rollback occurred",
        "Repair is required before the next mutation",
    )

    assert result.returncode == 0, f"post-tool hook should not throw: {result.stderr}"
    assert all(fragment in result.stdout for fragment in expected_fragments), (
        f"post-tool detection log missing expected fragments: {result.stdout}"
    )


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


@pytest.mark.parametrize(
    ("repo_mode", "response_mode"),
    (
        pytest.param("outside", "outside-unknown", id="outside-repo"),
        pytest.param("relaxed", "relaxed-unknown", id="relaxed-repo"),
    ),
)
def test_unknown_tool_is_advisory_outside_strict_repo(
    tmp_path: Path,
    repo_mode: str,
    response_mode: str,
) -> None:
    result = _run_plugin_contract(
        tmp_path,
        "tool.execute.before",
        response_mode,
        repo_mode,
    )

    assert result.returncode == 0, result.stderr
    assert "unknown OpenCode tool allowed" in result.stdout
