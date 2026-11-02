"""OpenCode V2 session scope and Code Mode exposure through the generated plugin."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

from slopgate._types import ObjectDict, object_dict, object_list
from slopgate.adapters.opencode_projection.models import OPENCODE_TOOL_CONTRACT_VERSION
from slopgate.context import build_context
from slopgate.engine import evaluate_payload
from slopgate.installer._opencode import render_opencode_plugin
from slopgate.resources import resource_path
from slopgate.state import RepairRequiredPayload, RepairTarget
from tests.integration.opencode_plugin_v2_support import (
    link_v2_dependencies,
    v2_before_input,
    v2_plugin_setup_source,
)

pytestmark = pytest.mark.skipif(shutil.which("bun") is None, reason="Bun is required")

_ENROLLMENT = "[slopgate]\nenabled = true\n"
_RECORDING_SLOPGATE = """#!/usr/bin/env python3
import json
import os
import sys

with open(os.environ["SLOPGATE_CALLS_PATH"], "a", encoding="utf-8") as calls:
    payload = json.load(sys.stdin) if sys.argv[1:2] == ["handle"] else None
    calls.write(json.dumps({"argv": sys.argv[1:], "payload": payload}) + "\\n")
if sys.argv[1:3] == ["repair", "status"]:
    print(json.dumps({"status": "CLEAN"}))
elif sys.argv[1:2] == ["handle"]:
    print(json.dumps({"action": "allow"}))
"""


@dataclass(frozen=True, slots=True)
class _Scope:
    directory: Path
    project: Path


def _nested_scope(tmp_path: Path) -> _Scope:
    project = tmp_path / "repo"
    directory = project / "sub"
    directory.mkdir(parents=True)
    (project / "slopgate.toml").write_text(_ENROLLMENT, encoding="utf-8")
    return _Scope(directory=directory, project=project)


def _run_runner(
    tmp_path: Path, scope: _Scope, statements: str
) -> subprocess.CompletedProcess[str]:
    executable = tmp_path / "slopgate"
    executable.write_text(_RECORDING_SLOPGATE, encoding="utf-8")
    executable.chmod(0o755)
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
        v2_plugin_setup_source(
            plugin_path, scope.directory, project_directory=scope.project
        )
        + statements,
        encoding="utf-8",
    )
    link_v2_dependencies(tmp_path)
    return subprocess.run(
        ["bun", "run", str(runner)],
        cwd=tmp_path,
        env=os.environ
        | {
            "SLOPGATE_BIN": str(executable),
            "SLOPGATE_CALLS_PATH": str(tmp_path / "calls.jsonl"),
        },
        text=True,
        capture_output=True,
        check=False,
    )


def _recorded_calls(tmp_path: Path, scope: _Scope) -> list[ObjectDict]:
    completed = _run_runner(
        tmp_path, scope, v2_before_input("read", "session", {"path": "a.py"})
    )
    assert completed.returncode == 0, completed.stderr
    lines = (tmp_path / "calls.jsonl").read_text(encoding="utf-8").splitlines()
    return [object_dict(json.loads(line)) for line in lines]


def _argument(call: ObjectDict, flag: str) -> str:
    argv = [str(item) for item in object_list(call["argv"])]
    return argv[argv.index(flag) + 1]


def test_repair_status_uses_project_worktree_from_subdirectory_session(
    tmp_path: Path,
) -> None:
    scope = _nested_scope(tmp_path)

    calls = _recorded_calls(tmp_path, scope)

    status = next(call for call in calls if call["payload"] is None)
    assert _argument(status, "--worktree") == str(scope.project), (
        "a subdirectory session must read the repair state of its project worktree"
    )
    assert _argument(status, "--cwd") == str(scope.directory), (
        "repair status must keep the session directory as its cwd"
    )


def test_enforcer_payload_separates_session_directory_from_worktree(
    tmp_path: Path,
) -> None:
    scope = _nested_scope(tmp_path)

    calls = _recorded_calls(tmp_path, scope)

    payload = object_dict(
        next(call["payload"] for call in calls if call["payload"] is not None)
    )
    assert payload["cwd"] == str(scope.directory), (
        "cwd must stay the session directory because host paths resolve against it"
    )
    assert payload["worktree"] == str(scope.project), (
        "worktree must identify the project so repair scope is shared"
    )


def test_filesystem_root_project_falls_back_to_session_directory(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "repo"
    directory.mkdir()
    (directory / "slopgate.toml").write_text(_ENROLLMENT, encoding="utf-8")
    # The host reports the filesystem root as the project of a non-git directory.
    scope = _Scope(directory=directory, project=Path(directory.anchor))

    calls = _recorded_calls(tmp_path, scope)

    status = next(call for call in calls if call["payload"] is None)
    assert _argument(status, "--worktree") == str(directory), (
        "the filesystem root must never become the repair worktree"
    )


def _arm_repair_at_project_root(project: Path) -> None:
    context = build_context({"cwd": str(project), "worktree": str(project)})
    context.state.mark_repair_required(
        "generation-1",
        RepairRequiredPayload(
            session_id="session",
            call_id="call",
            worktree=context.state.scope,
            targets=[RepairTarget("QUALITY-LINT-001", "a.py", "a.py", None, None)],
        ),
    )


def test_repair_armed_at_project_root_is_visible_from_subdirectory_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scope = _nested_scope(tmp_path)
    root = tmp_path / "slopgate-root"
    monkeypatch.setenv("SLOPGATE_ROOT", str(root))
    _arm_repair_at_project_root(scope.project)
    status_command = [sys.executable, "-m", "slopgate", "repair", "status"]

    completed = subprocess.run(
        status_command
        + ["--cwd", str(scope.directory), "--worktree", str(scope.project)],
        env=os.environ | {"SLOPGATE_ROOT": str(root)},
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    status = object_dict(json.loads(completed.stdout))
    assert status["generation"] == "generation-1", (
        "a subdirectory session must see the generation armed at the project root"
    )


def test_python_recovery_message_names_native_v2_mutation_tools(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scope = _nested_scope(tmp_path)
    monkeypatch.setenv("SLOPGATE_ROOT", str(tmp_path / "slopgate-root"))
    _arm_repair_at_project_root(scope.project)

    result = evaluate_payload(
        {
            "hook_event_name": "tool.execute.before",
            "tool_name": "custom_mutator",
            "tool_input": {},
            "cwd": str(scope.project),
            "worktree": str(scope.project),
            "session_id": "session",
            "opencode_tool_contract_version": OPENCODE_TOOL_CONTRACT_VERSION,
        },
        platform="opencode",
    )

    reason = str(object_dict(result.output)["reason"])
    assert "write, edit, patch" in reason, "patch is the native V2 mutation tool"
    assert "apply_patch" not in reason, "agents must not be told to use a V1 tool"


def test_verifier_is_a_direct_tool_outside_code_mode(tmp_path: Path) -> None:
    scope = _nested_scope(tmp_path)

    completed = _run_runner(
        tmp_path,
        scope,
        "process.stdout.write(JSON.stringify("
        '__slopgateTools["slopgate_verify_repair"].options ?? null))\n',
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout) == {"codemode": False}, (
        "the host hides tools without codemode=false behind execute, which would "
        "make the only in-session repair verifier unreachable"
    )
