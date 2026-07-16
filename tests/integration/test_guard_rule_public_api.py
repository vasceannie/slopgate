from __future__ import annotations

from pathlib import Path

import pytest

from slopgate import rules
from slopgate.config import load_config
from slopgate.context import HookContext
from slopgate.rules.common.quality.lint import _TouchedLintReport
from slopgate.rules.python_ast import PythonPytestAsyncioRule
from slopgate.state import HookStateStore
from slopgate.trace import TraceWriter
from slopgate.util.payloads import HookPayload

from tests.integration.config_override_support import (
    GuardRuleConfigOverrides,
    apply_guard_rule_config_overrides,
)
from tests.support import SKIP_UNIX_ONLY


def context_for_payload(
    tmp_path: Path,
    payload: dict[str, object],
    config_overrides: GuardRuleConfigOverrides | None = None,
) -> HookContext:
    config = load_config(
        root=tmp_path,
        repo_root=tmp_path,
        ensure_enrollment=False,
        ensure_trace=False,
    )
    if config_overrides is not None:
        config = apply_guard_rule_config_overrides(config, config_overrides)
    trace = TraceWriter(tmp_path / ".slopgate" / "trace")
    return HookContext(
        payload=HookPayload(payload, config),
        config=config,
        trace=trace,
        state=HookStateStore(trace.trace_dir),
    )


def write_payload(
    file_path: str, content: str, event: str = "PreToolUse"
) -> dict[str, object]:
    return {
        "session_id": "test-session",
        "hook_event_name": event,
        "tool_name": "Write",
        "tool_input": {"file_path": file_path, "content": content},
    }


def bash_payload(command: str, event: str = "PreToolUse") -> dict[str, object]:
    return {
        "session_id": "test-session",
        "hook_event_name": event,
        "tool_name": "Bash",
        "tool_input": {"command": command},
    }


def touched_lint_report_stub(ctx: HookContext) -> _TouchedLintReport:
    _ = ctx
    return _TouchedLintReport(
        ["long-test: 1"],
        [["[HOOK] long-test", "file: tests/test_sample.py"]],
        ["tests/test_sample.py"],
        {
            "collector": "long-test",
            "location": "tests/test_sample.py:1",
            "path": "tests/test_sample.py",
            "line": 1,
        },
    )


def test_baseline_guard_blocks_populated_baseline_creation(tmp_path: Path) -> None:
    ctx = context_for_payload(
        tmp_path,
        write_payload("baselines.json", '{"rules": {"new-rule": ["new-id"]}}'),
    )

    findings = rules.BaselineGuardRule().evaluate(ctx)

    assert [(item.rule_id, item.decision) for item in findings] == [
        ("BASELINE-001", "deny")
    ]


def test_search_reminder_reports_grep_without_search_tool(tmp_path: Path) -> None:
    ctx = context_for_payload(
        tmp_path,
        bash_payload("grep -R needle src"),
        config_overrides=GuardRuleConfigOverrides(
            search_reminder_message="Use rg before broad scans."
        ),
    )

    findings = rules.SearchReminderRule().evaluate(ctx)

    assert [(item.rule_id, item.additional_context) for item in findings] == [
        ("REMIND-SEARCH-001", "Use rg before broad scans.")
    ]


def test_post_edit_quality_rule_blocks_collector_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run_quality_commands(commands: list[str], ctx: HookContext) -> list[str]:
        _ = commands, ctx
        return ["$ quality\n[exit 1]\nfailed"]

    monkeypatch.setattr(
        "slopgate.rules.common.quality.postedit.run_quality_commands",
        fake_run_quality_commands,
    )
    ctx = context_for_payload(
        tmp_path,
        write_payload("sample.py", "print('x')\n", event="PostToolUse"),
        config_overrides=GuardRuleConfigOverrides(
            post_edit_quality_enabled=True,
            post_edit_quality_block_on_failure=True,
            post_edit_quality_commands={"python": ["quality {files}"]},
        ),
    )

    findings = rules.PostEditQualityRule().evaluate(ctx)

    assert [(item.rule_id, item.decision) for item in findings] == [
        ("QUALITY-POST-001", "block")
    ]


def test_post_edit_lint_rule_reports_touched_lint_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "slopgate.rules.common.quality.lint._collect_touched_lint_report",
        touched_lint_report_stub,
    )
    ctx = context_for_payload(
        tmp_path,
        write_payload(
            "tests/test_sample.py",
            "def test_x():\n    assert True\n",
            event="PostToolUse",
        ),
    )

    findings = rules.PostEditLintRule().evaluate(ctx)

    assert [(item.rule_id, item.metadata.get("paths")) for item in findings] == [
        ("QUALITY-LINT-001", ["tests/test_sample.py"])
    ], "post-edit lint rule should keep reporting touched paths"
    assert findings[0].metadata.get("first_diagnostic") == {
        "collector": "long-test",
        "location": "tests/test_sample.py:1",
        "path": "tests/test_sample.py",
        "line": 1,
    }, "post-edit lint rule should expose first diagnostic metadata"


def test_pytest_asyncio_rule_reports_unmarked_async_test(tmp_path: Path) -> None:
    source = "async def test_async_case():\n    await run_case()\n"
    ctx = context_for_payload(
        tmp_path, write_payload("tests/test_async_case.py", source)
    )

    findings = PythonPytestAsyncioRule().evaluate(ctx)

    assert [(item.rule_id, item.metadata.get("function")) for item in findings] == [
        ("PY-TEST-005", "test_async_case")
    ]


def test_repo_enrollment_rule_blocks_disable_sentinel_delete(tmp_path: Path) -> None:
    ctx = context_for_payload(
        tmp_path,
        write_payload("slopgate.toml", "[slopgate]\nenabled = false\n"),
    )

    findings = rules.RepoEnrollmentProtectionRule().evaluate(ctx)

    assert [item.rule_id for item in findings] == ["REPO-ENROLL-001"]


def test_ignore_preexisting_rule_blocks_dismissive_stop_response(
    tmp_path: Path,
) -> None:
    stop_ctx = context_for_payload(
        tmp_path,
        {
            "session_id": "stop-session",
            "hook_event_name": "Stop",
            "stop_response": "These were pre-existing failures.",
        },
    )

    findings = rules.IgnorePreexistingRule().evaluate(stop_ctx)

    assert [item.rule_id for item in findings] == ["STOP-001"]


def test_require_quality_check_rule_emits_stop_reminder(tmp_path: Path) -> None:
    ctx = context_for_payload(
        tmp_path,
        {
            "session_id": "quality-session",
            "hook_event_name": "Stop",
            "stop_response": "Implemented the change.",
        },
    )

    findings = rules.RequireQualityCheckRule().evaluate(ctx)

    assert [item.rule_id for item in findings] == ["STOP-002"]


def test_warn_large_file_rule_reports_large_content(tmp_path: Path) -> None:
    write_ctx = context_for_payload(
        tmp_path,
        write_payload("large.py", "x" * (rules.WarnLargeFileRule.MAX_CHARS + 1)),
    )

    findings = rules.WarnLargeFileRule().evaluate(write_ctx)

    assert [item.rule_id for item in findings] == ["WARN-LARGE-001"]


def test_hook_infra_exec_rule_exposes_global_rule_identifier() -> None:
    assert (
        rules.HookInfraExecProtectionRule().rule_id == "GLOBAL-BUILTIN-HOOK-INFRA-EXEC"
    )


def test_rulebook_security_rule_blocks_guardrail_disable(tmp_path: Path) -> None:
    rulebook_ctx = context_for_payload(
        tmp_path,
        write_payload("policy.json", '{"note": "disable guardrails"}'),
    )

    findings = rules.RulebookSecurityRule().evaluate(rulebook_ctx)

    assert [item.rule_id for item in findings] == ["BUILTIN-RULEBOOK-SECURITY"]


def test_session_start_context_rule_ignores_non_session_events(tmp_path: Path) -> None:
    session_ctx = context_for_payload(
        tmp_path,
        {"session_id": "session", "hook_event_name": "ConfigChange"},
    )

    findings = rules.SessionStartContextRule().evaluate(session_ctx)

    assert findings == []


def test_config_change_guard_rule_blocks_disable_all_hooks(tmp_path: Path) -> None:
    config_ctx = context_for_payload(
        tmp_path,
        {
            "session_id": "session",
            "hook_event_name": "ConfigChange",
            "source": "local_settings",
            "changes": {"disableAllHooks": True},
        },
    )

    findings = rules.ConfigChangeGuardRule().evaluate(config_ctx)

    assert [(item.rule_id, item.decision) for item in findings] == [
        ("CONFIG-001", "block")
    ]


@SKIP_UNIX_ONLY
def test_system_protection_rule_blocks_configured_system_path(tmp_path: Path) -> None:
    system_ctx = context_for_payload(
        tmp_path,
        write_payload("/etc/passwd", "root:x:0:0\n"),
        config_overrides=GuardRuleConfigOverrides(system_path_prefixes=["/etc"]),
    )

    findings = rules.SystemProtectionRule().evaluate(system_ctx)

    assert [item.rule_id for item in findings] == ["GLOBAL-BUILTIN-SYSTEM-PROTECTION"]


def test_git_no_verify_rule_blocks_hook_bypass(tmp_path: Path) -> None:
    git_ctx = context_for_payload(
        tmp_path, bash_payload("git commit --no-verify -m skip")
    )

    findings = rules.GitNoVerifyRule().evaluate(git_ctx)

    assert [item.rule_id for item in findings] == ["GIT-001"]
