from __future__ import annotations

from slopgate._types import ObjectDict
from tests.test_engine import (
    LoadFixture,
    Path,
    WriteBuilder,
    disabled_rule_findings,
    init_git_worktree,
    assert_blocked,
    evaluate_payload,
    finding_ids,
    hook_output,
    nested_output,
    output_string,
    pytest,
    require_output,
    required_string,
)


def test_permission_request_denies_makefile(bundle_root: Path) -> None:
    payload = {
        "session_id": "t",
        "cwd": str(bundle_root),
        "hook_event_name": "PermissionRequest",
        "tool_name": "Write",
        "tool_input": {"file_path": "Makefile", "content": "all:\n\techo hi\n"},
    }
    result = evaluate_payload(payload)
    inner = nested_output(hook_output(result), "decision")
    assert inner["behavior"] == "deny"
    assert "BUILTIN-PROTECTED-PATHS" in output_string(inner, "message")


def test_prompt_injects_context(bundle_root: Path) -> None:
    payload = {
        "session_id": "t",
        "cwd": str(bundle_root),
        "hook_event_name": "UserPromptSubmit",
        "prompt": "refactor the auth module",
    }
    result = evaluate_payload(payload)
    spec = hook_output(result)
    assert spec["hookEventName"] == "UserPromptSubmit"
    ctx = required_string(spec, "additionalContext")
    assert "Organization prompt context" in ctx
    assert "Repository Rules" in ctx


def test_long_param_list_blocks(tmp_project: Path) -> None:
    target = tmp_project / "src" / "sample.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("def build(a, b, c, d, e):\n    return a + b + c + d + e\n")
    payload = {
        "session_id": "t",
        "cwd": str(tmp_project),
        "hook_event_name": "PostToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": "src/sample.py", "content": target.read_text()},
        "tool_response": {"filePath": "src/sample.py", "success": True},
    }
    result = evaluate_payload(payload)
    assert_blocked(result)
    reason = required_string(require_output(result), "reason")
    assert "PY-CODE-009" in reason
    assert "parameters" in reason.lower()


def test_stop_preexisting_blocked(load_fixture: LoadFixture) -> None:
    result = evaluate_payload(load_fixture("stop_preexisting.json"))
    assert_blocked(result, "STOP-001")
    assert "STOP-001" in finding_ids(result), (
        "Stop responses claiming pre-existing failures should remain blocked"
    )


def test_subagent_stop_preexisting_blocked(bundle_root: Path) -> None:
    payload = {
        "session_id": "t",
        "cwd": str(bundle_root),
        "hook_event_name": "SubagentStop",
        "stop_response": "The type error was already existed before my changes.",
    }
    result = evaluate_payload(payload)
    assert_blocked(result, "STOP-001")
    assert "STOP-001" in finding_ids(result), (
        "SubagentStop responses claiming pre-existing failures should remain blocked"
    )


def test_clean_stop_gets_quality_reminder(bundle_root: Path) -> None:
    payload = {
        "session_id": "t",
        "cwd": str(bundle_root),
        "hook_event_name": "Stop",
        "stop_response": "All tasks completed successfully.",
    }
    result = evaluate_payload(payload)
    output = require_output(result)
    assert output_string(output, "decision") != "block"
    ctx = output_string(output, "systemMessage") or output_string(
        hook_output(result), "additionalContext"
    )
    assert "quality" in ctx.lower(), f"Expected quality reminder, got: {ctx}"


def test_git_commit_gets_quality_context(bundle_root: Path) -> None:
    payload = {
        "session_id": "t",
        "cwd": str(bundle_root),
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "git commit -m 'fix: something'"},
    }
    result = evaluate_payload(payload)
    output = require_output(result)
    ctx = output_string(output, "systemMessage") or output_string(
        hook_output(result), "additionalContext"
    )
    assert "quality" in ctx.lower()
    assert "GIT-002" in finding_ids(result)


def test_sessionstart_injects_git_context(tmp_path: Path) -> None:
    repo, _worktree = init_git_worktree(tmp_path)
    payload = {"session_id": "s", "cwd": str(repo), "hook_event_name": "SessionStart"}
    result = evaluate_payload(payload)
    spec = hook_output(result)
    assert spec["hookEventName"] == "SessionStart"
    ctx = required_string(spec, "additionalContext")
    assert "commits" in ctx.lower()
    assert "branch" in ctx.lower()


def test_sessionstart_injects_git_context_from_worktree(tmp_path: Path) -> None:
    _repo, worktree = init_git_worktree(tmp_path)
    payload = {
        "session_id": "t",
        "cwd": str(worktree),
        "hook_event_name": "SessionStart",
    }
    result = evaluate_payload(payload)
    spec = hook_output(result)
    assert spec["hookEventName"] == "SessionStart"
    ctx = required_string(spec, "additionalContext")
    assert "current branch" in ctx.lower()
    assert "feature/worktree-support" in ctx
    assert "recent commits" in ctx.lower()


def test_disable_all_hooks_blocked(load_fixture: LoadFixture) -> None:
    result = evaluate_payload(load_fixture("configchange_disable_hooks.json"))
    assert_blocked(result, "CONFIG-001")
    assert "CONFIG-001" in finding_ids(result), (
        "Config changes that disable all hooks should remain blocked"
    )


def test_hook_modification_blocked(bundle_root: Path) -> None:
    payload: ObjectDict = {
        "session_id": "t",
        "cwd": str(bundle_root),
        "hook_event_name": "ConfigChange",
        "source": "user_settings",
        "changes": {"hooks": {"PreToolUse": []}},
    }
    result = evaluate_payload(payload)
    assert_blocked(result, "CONFIG-001")
    assert "CONFIG-001" in finding_ids(result), (
        "Config changes that remove hook enforcement should remain blocked"
    )


def test_policy_settings_allowed(load_fixture: LoadFixture) -> None:
    result = evaluate_payload(load_fixture("configchange_safe.json"))
    assert result.output is None or result.output.get("decision") != "block", (
        f"Safe policy settings must not block, got: {result.output}"
    )


def test_large_file_warns(pretool_write: WriteBuilder) -> None:
    result = evaluate_payload(pretool_write("src/giant.py", "x = 1\n" * 60000))
    assert "WARN-LARGE-001" in finding_ids(result)
    ctx = required_string(hook_output(result), "additionalContext")
    assert "giant.py" in ctx
    assert "characters" in ctx.lower()


def test_small_file_no_warn(pretool_write: WriteBuilder) -> None:
    result = evaluate_payload(pretool_write("src/small.py", "x = 1\n"))
    assert "WARN-LARGE-001" not in finding_ids(result)


@pytest.mark.parametrize(
    "fixture_name, rule_id",
    [
        ("pretool_git_no_verify.json", "GIT-001"),
        ("pretool_silent_except.json", "PY-EXC-002"),
    ],
    ids=["python-rule-GIT-001", "regex-rule-PY-EXC-002"],
)
def test_disabled_rule_does_not_fire(
    load_fixture: LoadFixture, fixture_name: str, rule_id: str
) -> None:
    findings = disabled_rule_findings(load_fixture, fixture_name, rule_id)
    assert findings == [], f"Disabled {rule_id} should return no findings"
