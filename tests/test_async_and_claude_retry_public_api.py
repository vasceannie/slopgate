from __future__ import annotations

from hypothesis import assume, given, strategies

from slopgate.async_jobs import run_async_jobs
from slopgate.cli._claude_retry import claude_team_event_feedback
from slopgate.models import EngineResult, RuleFinding, Severity


def test_run_async_jobs_noops_outside_post_tool_use() -> None:
    assert run_async_jobs({"event_name": "PreToolUse"}) == ("", [])


def test_claude_team_event_feedback_renders_blocking_findings() -> None:
    result = EngineResult(
        event_name="TaskCompleted",
        findings=[
            RuleFinding(
                rule_id="RULE-001",
                title="Blocked",
                severity=Severity.HIGH,
                decision="block",
                message="repair required",
                additional_context="run focused tests",
            )
        ],
    )

    assert claude_team_event_feedback(result) == (
        "[RULE-001 | HIGH] repair required\n\nrun focused tests"
    )


def test_claude_team_event_feedback_ignores_non_retry_events() -> None:
    result = EngineResult(
        event_name="PreToolUse",
        findings=[
            RuleFinding(
                rule_id="RULE-001",
                title="Blocked",
                severity=Severity.HIGH,
                decision="block",
                message="repair required",
            )
        ],
    )

    assert claude_team_event_feedback(result) is None


@given(strategies.text(min_size=1, max_size=20))
def test_run_async_jobs_noops_for_non_post_tool_events(event_name: str) -> None:
    assume(event_name != "PostToolUse")

    assert run_async_jobs({"event_name": event_name}) == ("", [])


@given(strategies.text(min_size=1, max_size=20))
def test_claude_team_event_feedback_ignores_non_team_events(event_name: str) -> None:
    assume(event_name not in {"TaskCompleted", "TeammateIdle"})
    result = EngineResult(
        event_name=event_name,
        findings=[
            RuleFinding(
                rule_id="RULE-001",
                title="Blocked",
                severity=Severity.HIGH,
                decision="block",
                message="repair required",
            )
        ],
    )

    assert claude_team_event_feedback(result) is None
