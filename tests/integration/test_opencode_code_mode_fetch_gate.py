"""A Code Mode program's fetch is gated through the host permission hook."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from tests.integration.opencode_plugin_v2_support import (
    REPAIR_CLEAN,
    REPAIR_REQUIRED,
    ScriptedRepo,
    run_scripted_plugin,
    v2_before_input,
)

pytestmark = pytest.mark.skipif(shutil.which("bun") is None, reason="Bun is required")

_DISABLED = "[slopgate]\nenabled = false\n"
_START_EXECUTE = v2_before_input("execute", "session", {"code": "1"}, "execute-call")


def _finish(tool: str) -> str:
    return f"""await __slopgateHooks["execute.after"]({{
  tool: {json.dumps(tool)},
  sessionID: "session",
  agent: "build",
  messageID: "message",
  id: "execute-call",
  input: {{}},
  status: "completed",
  result: {{ content: "done" }},
}})
"""


def _evaluate_fetch(source_id: str = "execute-call") -> str:
    return f"""const evaluation = {{
  sessionID: "session",
  agent: "build",
  action: "webfetch",
  resources: ["http://example.test/"],
  metadata: {{ method: "GET", url: "http://example.test/" }},
  source: {{ type: "tool", messageID: "message", id: {json.dumps(source_id)} }},
  effect: "allow",
}}
await __slopgatePermissionHooks.evaluate(evaluation)
console.log(JSON.stringify(evaluation))
"""


def test_fetch_from_running_program_is_denied_during_repair(tmp_path: Path) -> None:
    evaluation = run_scripted_plugin(tmp_path, _START_EXECUTE + _evaluate_fetch())

    assert evaluation["effect"] == "deny", "a program must not reach the network"
    assert "slopgate_verify_repair" in str(evaluation["message"]), (
        "the program must learn how to clear repair"
    )


def test_direct_webfetch_stays_allowed_during_repair(tmp_path: Path) -> None:
    evaluation = run_scripted_plugin(
        tmp_path, _START_EXECUTE + _evaluate_fetch("direct-call")
    )

    assert evaluation["effect"] == "allow", (
        "the declared read-only webfetch tool must keep working during repair"
    )


def test_fetch_is_denied_when_repair_arms_after_the_program_starts(
    tmp_path: Path,
) -> None:
    arm = f"await Bun.write(process.env.FAKE_REPAIR_STATE, {json.dumps(REPAIR_REQUIRED)})\n"

    evaluation = run_scripted_plugin(
        tmp_path,
        _START_EXECUTE + arm + _evaluate_fetch(),
        ScriptedRepo(state=REPAIR_CLEAN),
    )

    assert evaluation["effect"] == "deny", (
        "repair state must be read per request, not when execute started"
    )


def test_inner_tool_completion_keeps_the_program_gated(tmp_path: Path) -> None:
    evaluation = run_scripted_plugin(
        tmp_path,
        _START_EXECUTE + _finish("opencode_worktree_list") + _evaluate_fetch(),
    )

    assert evaluation["effect"] == "deny", (
        "inner tools share the execute call ID, so finishing one must not end gating"
    )


def test_finished_program_no_longer_matches_a_permission_source(
    tmp_path: Path,
) -> None:
    evaluation = run_scripted_plugin(
        tmp_path, _START_EXECUTE + _finish("execute") + _evaluate_fetch()
    )

    assert evaluation["effect"] == "allow", (
        "gating must end with the execute call that started it"
    )


_UNGATED_REPOS = (
    pytest.param(ScriptedRepo(state=REPAIR_CLEAN), id="clean"),
    pytest.param(ScriptedRepo(enrollment=_DISABLED), id="relaxed-repo"),
    pytest.param(ScriptedRepo(enrollment=None), id="outside-repo"),
)


@pytest.mark.parametrize("repo", _UNGATED_REPOS)
def test_fetch_is_untouched_outside_an_armed_strict_repo(
    tmp_path: Path, repo: ScriptedRepo
) -> None:
    evaluation = run_scripted_plugin(
        tmp_path, _START_EXECUTE + _evaluate_fetch(), repo
    )

    assert evaluation["effect"] == "allow", "no repair gate applies here"


def test_fetch_fails_closed_when_repair_state_is_unavailable(tmp_path: Path) -> None:
    evaluation = run_scripted_plugin(
        tmp_path, _START_EXECUTE + _evaluate_fetch(), ScriptedRepo(state="")
    )

    assert evaluation["effect"] == "deny", (
        "a managed repo must not open the network on unreadable state"
    )
