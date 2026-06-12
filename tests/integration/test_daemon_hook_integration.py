from __future__ import annotations

from collections.abc import Callable
import importlib
from typing import Protocol, cast


class _ObjectFactory(Protocol):
    def __call__(self, **kwargs: object) -> object: ...


class _ResponseLike(Protocol):
    exit_code: int
    stderr: str | None


class _Evaluator(Protocol):
    def __call__(self, payload: dict[str, object], *, platform: str) -> object: ...


class _DaemonModule(Protocol):
    CLAUDE_TEAM_EVENT_EXIT_CODE: int
    DaemonRequest: _ObjectFactory
    evaluate_hook_request: Callable[[object], _ResponseLike]


class _HookModule(Protocol):
    PLATFORM_CLAUDE: str
    evaluate_payload: _Evaluator
    claude_team_event_feedback: Callable[[object], str | None]


class _SeverityModule(Protocol):
    HIGH: object


class _ModelsModule(Protocol):
    EngineResult: _ObjectFactory
    RuleFinding: _ObjectFactory
    Severity: _SeverityModule


daemon = cast(_DaemonModule, importlib.import_module("slopgate.daemon"))
daemon_hook = cast(_HookModule, importlib.import_module("slopgate.daemon.hook"))
models = cast(_ModelsModule, importlib.import_module("slopgate.models"))


class _BlockingClaudeEvaluation:
    def __call__(self, payload: dict[str, object], *, platform: str) -> object:
        _ = payload
        return models.EngineResult(
            event_name="TaskCompleted",
            findings=[
                models.RuleFinding(
                    rule_id="RULE-001",
                    title="Blocked",
                    severity=models.Severity.HIGH,
                    decision="block",
                    message=f"{platform} repair required",
                    additional_context="run focused tests",
                )
            ],
        )


def test_daemon_hook_preserves_claude_team_event_feedback_contract() -> None:
    original_evaluate = daemon_hook.evaluate_payload
    evaluation = _BlockingClaudeEvaluation()
    try:
        daemon_hook.evaluate_payload = evaluation
        expected_feedback = daemon_hook.claude_team_event_feedback(
            evaluation(
                {"command": "pytest"},
                platform=daemon_hook.PLATFORM_CLAUDE,
            )
        )
        response = daemon.evaluate_hook_request(
            daemon.DaemonRequest(
                payload={"command": "pytest"},
                platform=daemon_hook.PLATFORM_CLAUDE,
            )
        )
    finally:
        daemon_hook.evaluate_payload = original_evaluate

    assert response.exit_code == daemon.CLAUDE_TEAM_EVENT_EXIT_CODE, (
        "Claude feedback exits 2"
    )
    assert response.stderr == f"{expected_feedback}\n", (
        "Daemon should preserve feedback"
    )
