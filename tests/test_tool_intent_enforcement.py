from __future__ import annotations

from pathlib import Path

import pytest

from slopgate.adapters import get_adapter
from slopgate.engine import evaluate_payload
from slopgate.util.payloads import (
    find_command_has_mutation,
    is_mutating_tool_use,
    is_read_only_tool_use,
    platform_event_name,
    tool_intent,
)
from tests.engine.support import (
    enable_failing_post_edit_quality_command,
    write_config_from_defaults,
)
from tests.test_engine import finding_ids


CODEX_EVENT_CASES = (
    pytest.param("SessionStart", "SessionStart", id="session_start"),
    pytest.param("SubagentStart", "SubagentStart", id="subagent_start"),
    pytest.param("PreToolUse", "PreToolUse", id="pre_tool_use"),
    pytest.param("PermissionRequest", "PermissionRequest", id="permission_request"),
    pytest.param("PostToolUse", "PostToolUse", id="post_tool_use"),
    pytest.param("PreCompact", "PreCompact", id="pre_compact"),
    pytest.param("PostCompact", "PostCompact", id="post_compact"),
    pytest.param("UserPromptSubmit", "UserPromptSubmit", id="user_prompt_submit"),
    pytest.param("SubagentStop", "SubagentStop", id="subagent_stop"),
    pytest.param("Stop", "Stop", id="stop"),
)

OPENCODE_EVENT_CASES = (
    pytest.param("tool.execute.before", "PreToolUse", id="tool_before"),
    pytest.param("tool.execute.after", "PostToolUse", id="tool_after"),
    pytest.param("permission.asked", "PermissionRequest", id="permission_asked"),
    pytest.param("permission.replied", "PermissionReplied", id="permission_replied"),
    pytest.param("session.created", "SessionStart", id="session_created"),
    pytest.param(
        "session.compaction.ended", "PostCompact", id="session_compaction_ended"
    ),
    pytest.param("session.idle", "Stop", id="session_idle"),
    pytest.param(
        "session.execution.failed", "SessionError", id="session_execution_failed"
    ),
    pytest.param("session.status", "SessionStatus", id="session_status"),
)


def _pretool_bash_payload(cwd: Path, command: str) -> dict[str, object]:
    return {
        "session_id": "intent-test",
        "cwd": str(cwd),
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }


def _posttool_payload(
    cwd: Path, tool_name: str, tool_input: dict[str, object]
) -> dict[str, object]:
    return {
        "session_id": "intent-test",
        "cwd": str(cwd),
        "hook_event_name": "PostToolUse",
        "tool_name": tool_name,
        "tool_input": tool_input,
    }


def _opencode_native_posttool_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tool_name: str,
    tool_input: dict[str, object],
) -> dict[str, object]:
    write_config_from_defaults(
        tmp_path,
        monkeypatch,
        enable_failing_post_edit_quality_command,
    )
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / "slopgate.toml").write_text("[slopgate]\nenabled = true\n")
    _ = (repo / "app.py").write_text("print('ok')\n")
    return {
        "session_id": "intent-test",
        "cwd": str(repo),
        "hook_event_name": "tool.execute.after",
        "tool_name": tool_name,
        "tool_input": tool_input,
    }


@pytest.mark.parametrize(("raw_event", "canonical_event"), CODEX_EVENT_CASES)
def test_codex_normalizes_documented_hook_events(
    raw_event: str, canonical_event: str
) -> None:
    normalized = get_adapter("codex").normalize_payload(
        {"session_id": "intent-test", "hook_event_name": raw_event}
    )

    assert normalized["hook_event_name"] == canonical_event, "Codex event mismatch"


@pytest.mark.parametrize(("raw_event", "canonical_event"), OPENCODE_EVENT_CASES)
def test_opencode_normalizes_documented_plugin_events(
    raw_event: str, canonical_event: str
) -> None:
    normalized = get_adapter("opencode").normalize_payload(
        {"session_id": "intent-test", "hook_event_name": raw_event}
    )

    assert normalized["hook_event_name"] == canonical_event, "OpenCode event mismatch"


@pytest.mark.parametrize(
    ("raw_event", "tool_name", "expected_intent"),
    [
        pytest.param("beforeReadFile", "Read", "read", id="before_read_file"),
        pytest.param("beforeTabFileRead", "Read", "read", id="before_tab_read"),
        pytest.param("preToolUse", "grep", "search", id="grep_tool"),
    ],
)
def test_cursor_read_events_normalize_to_read_only_intent(
    raw_event: str, tool_name: str, expected_intent: str
) -> None:
    normalized = get_adapter("cursor").normalize_payload(
        {
            "session_id": "intent-test",
            "hook_event_name": raw_event,
            "tool_name": tool_name,
            "filePath": "tests/quality/check.py",
        }
    )

    assert tool_intent(normalized) == expected_intent, "Cursor intent mismatch"


@pytest.mark.parametrize(
    ("command", "expected_intent"),
    [
        pytest.param("rtk read slopgate.toml", "read", id="rtk_read"),
        pytest.param("rg needle dashboard/package.json", "search", id="rg_search"),
        pytest.param("ls src/slopgate", "list", id="ls_list"),
        pytest.param("sed -n '1,80p' pyproject.toml", "read", id="sed_print"),
    ],
)
def test_tool_intent_classifies_safe_shell_reads(
    command: str, expected_intent: str, tmp_path: Path
) -> None:
    payload = _pretool_bash_payload(tmp_path, command)

    assert tool_intent(payload) == expected_intent, f"{command} intent should match"


def test_read_only_tool_use_public_api_reports_safe_shell_read(tmp_path: Path) -> None:
    payload = _pretool_bash_payload(tmp_path, "rtk read slopgate.toml")

    assert is_read_only_tool_use(payload), "rtk read should be read-only"


@pytest.mark.parametrize(
    "command",
    [
        pytest.param("sed -i 's/a/b/' pyproject.toml", id="sed_in_place"),
        pytest.param("echo enabled > slopgate.toml", id="redirect"),
        pytest.param("printf x | tee pyproject.toml", id="tee"),
        pytest.param("find . -name '*.py' -delete", id="find_delete"),
    ],
)
def test_tool_intent_classifies_mutating_shell_commands(
    command: str, tmp_path: Path
) -> None:
    payload = _pretool_bash_payload(tmp_path, command)

    assert tool_intent(payload) == "mutate", f"{command} should be mutating"


def test_mutating_tool_use_public_api_reports_redirect(tmp_path: Path) -> None:
    payload = _pretool_bash_payload(tmp_path, "echo enabled > slopgate.toml")

    assert is_mutating_tool_use(payload), "redirect should be mutating"


def test_find_command_has_mutation_detects_delete_action() -> None:
    tokens = ["find", ".", "-name", "*.py", "-delete"]

    assert find_command_has_mutation(tokens), "find -delete should be mutating"


def test_reading_slopgate_toml_does_not_emit_edit_only_denials(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / "slopgate.toml").write_text("[slopgate]\nenabled = true\n")

    result = evaluate_payload(_pretool_bash_payload(repo, "rtk read slopgate.toml"))

    ids = finding_ids(result)
    assert "REPO-ENROLL-001" not in ids, "read should not trip enrollment edit guard"
    assert "BUILTIN-PROTECTED-PATHS" not in ids, "read should not trip path edit guard"


def test_executing_quality_test_path_does_not_emit_edit_only_denial(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / "slopgate.toml").write_text("[slopgate]\nenabled = true\n")

    payload = _pretool_bash_payload(
        repo,
        "rtk pytest "
        "tests/quality/test_private_import_boundaries.py::"
        "test_no_cross_package_private_imports -x -q",
    )

    result = evaluate_payload(payload)
    ids = finding_ids(result)
    assert tool_intent(payload) == "execute", "pytest invocation should stay executable"
    assert "BUILTIN-PROTECTED-PATHS" not in ids, (
        "test execution should not trip path edit guard"
    )


def test_mutating_slopgate_toml_still_emits_enrollment_denial(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / "slopgate.toml").write_text("[slopgate]\nenabled = true\n")

    result = evaluate_payload(
        _pretool_bash_payload(repo, "printf '[slopgate]\\n' > slopgate.toml")
    )

    assert "REPO-ENROLL-001" in finding_ids(result), "mutation should stay denied"


def test_posttool_read_skips_quality_and_records_intent(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _ = (repo / "slopgate.toml").write_text("[slopgate]\nenabled = true\n")
    _ = (repo / "app.py").write_text("print('ok')\n")

    result = evaluate_payload(_posttool_payload(repo, "Read", {"file_path": "app.py"}))

    ids = finding_ids(result)
    assert "QUALITY-POST-001" not in ids, "read must skip post-edit quality"
    assert "QUALITY-LINT-001" not in ids, "read must skip touched-file lint"


@pytest.mark.parametrize(
    ("tool_name", "tool_input"),
    [
        pytest.param(
            "write",
            {"path": "app.py", "content": "print('updated')\n"},
            id="native_write",
        ),
        pytest.param(
            "edit",
            {
                "path": "app.py",
                "oldString": "print('ok')\n",
                "newString": "print('updated')\n",
            },
            id="native_edit",
        ),
    ],
)
def test_opencode_native_posttool_mutation_runs_post_edit_quality(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tool_name: str,
    tool_input: dict[str, object],
) -> None:
    payload = _opencode_native_posttool_payload(
        tmp_path,
        monkeypatch,
        tool_name,
        tool_input,
    )

    result = evaluate_payload(payload, platform="opencode")

    assert "QUALITY-POST-001" in finding_ids(result), (
        f"native {tool_name} should route through post-edit quality"
    )


def test_platform_event_name_prefers_original_opencode_event() -> None:
    normalized = get_adapter("opencode").normalize_payload(
        {"session_id": "intent-test", "hook_event_name": "session.execution.failed"}
    )

    assert platform_event_name(normalized) == "session.execution.failed", (
        "original event kept"
    )
