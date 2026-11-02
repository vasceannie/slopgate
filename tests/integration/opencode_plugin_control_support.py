from __future__ import annotations

import json
import os
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from slopgate.installer._opencode import render_opencode_plugin
from slopgate.resources import resource_path
from tests.integration.opencode_plugin_v2_support import (
    link_v2_dependencies,
    v2_after_error_input,
    v2_after_input,
    v2_plugin_setup_source,
)


_DEFAULT_TOOL_ARGS: dict[str, object] = {
    "path": "sample.py",
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
    "repair-required-wrapper-task": {"category": "quick", "prompt": "edit sample.py"},
}
_TOOL_NAME_BY_MODE = {
    "repair-unavailable-read": "read",
    "repair-unavailable-read-block": "read",
    "repair-unavailable-read-collision": "r_e_a_d",
    "repair-unavailable-apply-patch": "patch",
    "clean-enforcer-unavailable-apply-patch": "patch",
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
    "repair-required-unknown-generation": "custom_mutator",
}


def assert_recovery_protocol(stderr: str) -> None:
    """Require the repair gate to render its imperative recovery protocol."""
    assert "STOP" in stderr, f"protocol must open with STOP: {stderr}"
    assert "do not retry this blocked mutation" in stderr, (
        f"missing no-retry directive: {stderr}"
    )
    assert "equivalent retries remain blocked" in stderr, (
        f"missing blocked-retry statement: {stderr}"
    )
    assert "slopgate repair status --cwd" not in stderr, (
        f"blocked status command must not be advertised: {stderr}"
    )
    assert "read the first causal finding: PY-CODE-013 in " in stderr, (
        f"missing causal finding render: {stderr}"
    )
    assert "src/sample.py" in stderr, f"missing canonical target suffix: {stderr}"
    assert "slopgate repair verify --cwd" not in stderr, (
        f"blocked verify command must not be advertised: {stderr}"
    )
    assert "write, edit, patch" in stderr, f"missing allowed mutation tools: {stderr}"
    assert "slopgate_verify_repair" in stderr, f"missing repair verifier tool: {stderr}"
    assert "slopgate lint check" in stderr, f"missing exact lint gate: {stderr}"


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
    if mode.startswith("repair-unavailable"):
        print("repair state unavailable", file=sys.stderr)
        raise SystemExit(2)
    status = "REPAIR_REQUIRED" if mode.startswith("repair-required") else "CLEAN"
    worktree = os.path.realpath(sys.argv[sys.argv.index("--worktree") + 1])
    target = os.path.join(worktree, "src", "sample.py")
    state = {
        "status": status,
        "worktree": worktree,
        "rule_ids": ["PY-CODE-013"],
        "paths": [target],
        "targets": [{
            "rule_id": "PY-CODE-013",
            "path": target,
            "raw_path": "src/sample.py",
            "function": "sample",
            "error": None,
        }],
    }
    if mode != "repair-required-unknown-generation":
        state["generation"] = "generation-1"
    print(json.dumps(state))
else:
    payload = json.load(sys.stdin)
    if mode == "empty-success":
        print("")
    elif mode == "assert-completed":
        if (
            payload.get("hook_event_name") != "tool.execute.after"
            or payload.get("execution_outcome") != "returned"
            or payload.get("tool_output") != "completed"
            or payload.get("tool_result") != {"content": "completed", "metadata": {}}
        ):
            raise SystemExit("completed result was not forwarded with typed fields")
        print(json.dumps({"action": "warn", "reason": "completed-result-observed"}))
    elif mode == "assert-failed":
        if (
            payload.get("hook_event_name") != "tool.execute.after"
            or payload.get("execution_outcome") != "failed"
            or payload.get("tool_error") != "failed"
        ):
            raise SystemExit("failed result was not forwarded with typed fields")
        print(json.dumps({"action": "warn", "reason": "failed-result-observed"}))
    elif mode == "event-sentinel":
        print(json.dumps({"action": "warn", "reason": "foreign-event-observed"}))
    elif mode == "mutate":
        print(json.dumps({"action": "allow", "updated_args": {"content": "mutated"}}))
    elif mode.startswith("repair-required-command"):
        print(json.dumps({"action": "allow"}))
    elif mode in {"unknown-readonly", "repair-unavailable-read", "repair-unavailable-apply-patch",
                  "clean-enforcer-unavailable-apply-patch"}:
        raise SystemExit(2)
    elif mode == "unknown-effect":
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
    events: Sequence[Mapping[str, object]] | None = None,
) -> Path:
    selected_args = _TOOL_ARGS_BY_MODE.get(response_mode, _DEFAULT_TOOL_ARGS)
    tool_name = (
        "bash"
        if response_mode.startswith("repair-required-command")
        else _TOOL_NAME_BY_MODE.get(response_mode, "write")
    )
    runner = tmp_path / "runner.ts"
    runner.write_text(
        v2_plugin_setup_source(plugin_path, tmp_path, events)
        + f"""
const output = {{ args: {json.dumps(selected_args)} }}
const beforeInput = {{
  tool: {json.dumps(tool_name)},
  sessionID: "session",
  agent: "build",
  messageID: "message",
  id: "call",
  input: output.args,
}}
if ({json.dumps(native_event)} === "event.stream") {{
  await new Promise((resolve) => setTimeout(resolve, 25))
}} else if (
  {json.dumps(native_event)} === "tool.execute.after"
  && {json.dumps(response_mode)} === "assert-failed"
) {{
{v2_after_error_input(tool_name, "session", selected_args)}
}} else if ({json.dumps(native_event)} === "tool.execute.after") {{
{v2_after_input(tool_name, "session", selected_args)}
}} else {{
  await __slopgateHooks["execute.before"](beforeInput)
  output.args = beforeInput.input
}}
if (__slopgateCleanup) await __slopgateCleanup()
console.log(JSON.stringify({{ logs: __slopgateLogs, args: output.args, streamAborted: __slopgateEventState.aborted }}))
""",
        encoding="utf-8",
    )
    return runner


def run_plugin_contract(
    tmp_path: Path,
    native_event: str,
    response_mode: str = "block",
    repo_mode: str = "strict",
    events: Sequence[Mapping[str, object]] | None = None,
) -> subprocess.CompletedProcess[str]:
    executable = _write_fake_slopgate(tmp_path, repo_mode)
    plugin_path = tmp_path / "slopgate-plugin.ts"
    plugin_path.write_text(
        render_opencode_plugin(
            resource_path("opencode_plugin.ts").read_text(encoding="utf-8"),
            str(executable),
            {"opencode_version": "2.2.5"},
        ),
        encoding="utf-8",
    )
    runner = _write_plugin_runner(
        tmp_path, plugin_path, native_event, response_mode, events
    )
    link_v2_dependencies(tmp_path)
    return subprocess.run(
        ["bun", "run", str(runner)],
        cwd=tmp_path,
        env=os.environ
        | {"SLOPGATE_BIN": str(executable), "CONTRACT_RESPONSE_MODE": response_mode},
        text=True,
        capture_output=True,
        check=False,
    )
