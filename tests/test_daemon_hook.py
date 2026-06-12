from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import importlib
from typing import Protocol, cast

from hypothesis import given, strategies


class _ObjectFactory(Protocol):
    def __call__(self, **kwargs: object) -> object: ...


class _DaemonResponseLike(Protocol):
    ok: bool
    output: dict[str, object]
    stderr: str | None
    exit_code: int


class _Evaluator(Protocol):
    def __call__(self, payload: dict[str, object], *, platform: str) -> object: ...


class _FeedbackRenderer(Protocol):
    def __call__(self, result: object) -> str: ...


class _DaemonModule(Protocol):
    CLAUDE_TEAM_EVENT_EXIT_CODE: int
    DaemonRequest: _ObjectFactory
    evaluate_hook_request: Callable[[object], _DaemonResponseLike]


class _HookModule(Protocol):
    evaluate_payload: _Evaluator
    claude_team_event_feedback: _FeedbackRenderer


daemon = cast(_DaemonModule, importlib.import_module("slopgate.daemon"))
daemon_hook = cast(_HookModule, importlib.import_module("slopgate.daemon.hook"))


@dataclass(slots=True)
class _EvaluationResult:
    output: dict[str, object]


class _EvaluatePayloadStub:
    def __init__(self, output: dict[str, object]) -> None:
        self.output = output
        self.payload: dict[str, object] | None = None
        self.platform: str | None = None

    def __call__(
        self, payload: dict[str, object], *, platform: str
    ) -> _EvaluationResult:
        self.payload = payload
        self.platform = platform
        return _EvaluationResult(output=self.output)


class _ClaudeFeedbackStub:
    def __init__(self, feedback: str) -> None:
        self.feedback = feedback

    def __call__(self, result: object) -> str:
        _ = result
        return self.feedback


def _install_daemon_hook_stubs(
    *, feedback: str, output: dict[str, object]
) -> _EvaluatePayloadStub:
    evaluator = _EvaluatePayloadStub(output)
    daemon_hook.evaluate_payload = evaluator
    daemon_hook.claude_team_event_feedback = _ClaudeFeedbackStub(feedback)
    return evaluator


def _evaluate_with_stubbed_hook(
    request: object,
    *,
    feedback: str,
    output: dict[str, object],
) -> tuple[_EvaluatePayloadStub, _DaemonResponseLike]:
    original_evaluate = daemon_hook.evaluate_payload
    original_feedback = daemon_hook.claude_team_event_feedback
    try:
        evaluator = _install_daemon_hook_stubs(feedback=feedback, output=output)
        response = daemon.evaluate_hook_request(request)
    finally:
        daemon_hook.evaluate_payload = original_evaluate
        daemon_hook.claude_team_event_feedback = original_feedback
    return evaluator, response


def _platform_normalization_observation(platform: str | None) -> tuple[str | None, str]:
    expected_platform = (platform or "claude").strip().lower()
    evaluator, _response = _evaluate_with_stubbed_hook(
        daemon.DaemonRequest(payload={"command": "probe"}, platform=platform),
        feedback="",
        output={"decision": "allow"},
    )
    return evaluator.platform, expected_platform


def test_evaluate_hook_request_returns_engine_output() -> None:
    evaluator, response = _evaluate_with_stubbed_hook(
        daemon.DaemonRequest(
            payload={"command": "pytest"}, platform="codex", event="handle"
        ),
        feedback="",
        output={"decision": "allow"},
    )

    assert response.ok is True, "Daemon hook handler should return successful responses"
    assert response.output == {"decision": "allow"}, (
        "Handler should expose engine output"
    )
    assert evaluator.payload == {"command": "pytest"}, "Handler should forward payload"
    assert evaluator.platform == "codex", "Handler should normalize platform for engine"


def test_evaluate_hook_request_preserves_claude_feedback_exit() -> None:
    _evaluator, response = _evaluate_with_stubbed_hook(
        daemon.DaemonRequest(payload={"command": "pytest"}, platform="claude"),
        feedback="repair this",
        output={},
    )

    assert response.stderr == "repair this\n", (
        "Claude feedback should be emitted on stderr"
    )
    assert response.exit_code == daemon.CLAUDE_TEAM_EVENT_EXIT_CODE, (
        "Claude feedback should preserve the direct CLI exit code"
    )


def test_evaluate_hook_request_empty_payload_matches_cli_noop() -> None:
    evaluator, response = _evaluate_with_stubbed_hook(
        daemon.DaemonRequest(payload={}, platform="claude"),
        feedback="repair this",
        output={"decision": "deny"},
    )

    assert response.ok is True, "Empty daemon payload should be accepted as a no-op"
    assert response.output == {}, "Empty daemon payload should not emit hook output"
    assert response.stderr is None, "Empty daemon payload should not emit feedback"
    assert evaluator.payload is None, "Empty daemon payload should not run the engine"


@given(
    platform=strategies.one_of(strategies.none(), strategies.text(max_size=12)),
)
def test_evaluate_hook_request_platform_branch_property(
    platform: str | None,
) -> None:
    observed_platform, expected_platform = _platform_normalization_observation(platform)

    assert observed_platform == expected_platform, "Handler should normalize platform"
