"""OpenCode execution and mutation outcomes remain independent in traces."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import pytest

from slopgate._types import object_dict
from slopgate.constants import BLOCK, PLATFORM_OPENCODE
from slopgate.context import HookContext
from slopgate.engine._evaluation import _record_opencode_repair_required
from slopgate.engine._trace_payloads import (
    EvaluationMetadata,
    evaluation_metadata,
    payload_for_done,
    subprocess_startup_ms,
    write_start_trace,
)
from slopgate.models import ContentTarget, RuleFinding, Severity
from tests.test_engine import (
    MonkeyPatch,
    evaluate_payload,
    keep_default_config,
    pretool_bash_payload,
    write_config_from_defaults,
    write_slopgate,
)

_TIMING_PHASES = (
    "collector_ms",
    "evaluation_ms",
    "normalization_context_ms",
    "render_ms",
    "rule_engine_ms",
    "subprocess_startup_ms",
    "trace_event_ms",
)
_TRACE_PAYLOAD_CALLABLES = (
    evaluation_metadata,
    payload_for_done,
    subprocess_startup_ms,
    write_start_trace,
)


@dataclass(frozen=True, slots=True)
class OutcomeCase:
    execution_outcome: str
    mutation_outcome: str
    evidence_tier: dict[str, str]


@dataclass(slots=True)
class _RepairStateSpy:
    marked: list[object] = field(default_factory=list)
    cleared: list[str] = field(default_factory=list)

    def repair_generation(self, **_kwargs: object) -> str:
        return "generation-1"

    def mark_repair_required(self, *args: object) -> None:
        self.marked.append(args)

    def get_repair_required(self) -> dict[str, str]:
        return {"generation": "generation-1"}

    def clear_repair_required(self, generation: str) -> bool:
        self.cleared.append(generation)
        return True


@dataclass(slots=True)
class _RepairPayloadSpy:
    payload: dict[str, object]


@dataclass(slots=True)
class _RepairContextSpy:
    event_name: str
    payload: _RepairPayloadSpy
    session_id: str
    content_targets: list[ContentTarget]
    state: _RepairStateSpy
    mutating: bool


def _repair_context(
    *,
    execution_outcome: str = "",
    mutating: bool = False,
    state: _RepairStateSpy | None = None,
) -> _RepairContextSpy:
    payload: dict[str, object] = {"call_id": "call-1"}
    if execution_outcome:
        payload["execution_outcome"] = execution_outcome
    return _RepairContextSpy(
        event_name="PostToolUse",
        payload=_RepairPayloadSpy(payload),
        session_id="session-1",
        content_targets=[ContentTarget("src/app.py", "value = 1", "tool_input")],
        state=state if state is not None else _RepairStateSpy(),
        mutating=mutating,
    )


def _blocking_finding() -> RuleFinding:
    return RuleFinding(
        rule_id="PY-CODE-010",
        title="long line",
        severity=Severity.MEDIUM,
        decision=BLOCK,
    )


def test_trace_payload_interface_keeps_typed_metadata_and_timing_contract(
    tmp_path: Path,
) -> None:
    metadata = EvaluationMetadata(
        "opencode", "opencode", "repo_strict", tmp_path, "partial", None
    )

    assert metadata.repo_root_text == str(tmp_path), (
        "trace metadata should serialize the resolved repository root"
    )
    assert subprocess_startup_ms({}) == 0, (
        "missing plugin timestamps should report zero startup latency"
    )
    assert all(callable(helper) for helper in _TRACE_PAYLOAD_CALLABLES), (
        "the evaluation orchestrator should receive callable trace boundaries"
    )


@pytest.mark.parametrize("execution_outcome", ("failed", "cancelled"))
def test_failed_opencode_execution_does_not_create_repair_lock(
    execution_outcome: str,
) -> None:
    context = _repair_context(execution_outcome=execution_outcome)

    _record_opencode_repair_required(
        cast(HookContext, context), [_blocking_finding()], PLATFORM_OPENCODE
    )

    assert context.state.marked == [], (
        "failed executions must not create persistent repair state"
    )


def test_clean_completed_opencode_mutation_clears_repair_lock() -> None:
    context = _repair_context(execution_outcome="returned", mutating=True)

    _record_opencode_repair_required(cast(HookContext, context), [], PLATFORM_OPENCODE)

    assert context.state.cleared == ["generation-1"], (
        "a clean completed repair mutation should clear its pending generation"
    )


def _latest_result_row(tmp_path: Path) -> dict[str, object]:
    results_path = tmp_path / "vf-root" / "logs" / "results.jsonl"
    lines = results_path.read_text(encoding="utf-8").strip().splitlines()
    assert lines, "OpenCode evaluation should write a results trace row"
    return json.loads(lines[-1])


def _evaluate_opencode_outcome(
    tmp_path: Path, monkeypatch: MonkeyPatch, case: OutcomeCase
) -> dict[str, object]:
    repo = write_slopgate(tmp_path / "repo_opencode_outcomes")
    write_config_from_defaults(tmp_path, monkeypatch, keep_default_config)
    monkeypatch.setenv("SLOPGATE_ROOT", str(tmp_path / "vf-root"))
    payload = pretool_bash_payload(repo, "git status")
    payload.update(
        {
            "hook_event_name": "tool.execute.after",
            "tool_name": "Read",
            "tool_input": {"file_path": "src/app.py"},
            "worktree": str(repo),
            "opencode_session_id": "session-opencode",
            "call_id": "call-opencode",
            "tool_title": "Read",
            "tool_metadata": {"source": "opencode"},
            "tool_output": {"content": "raw after output"},
            "execution_outcome": case.execution_outcome,
            "mutation_outcome": case.mutation_outcome,
            "evidence_tier": case.evidence_tier,
        }
    )
    _ = evaluate_payload(payload, platform="opencode")
    return _latest_result_row(tmp_path)


@pytest.mark.parametrize(
    "case",
    (
        pytest.param(
            OutcomeCase(
                "returned",
                "unknown",
                {"execution": "pinned-source", "mutation": "unresolved"},
            ),
            id="normal-return",
        ),
        pytest.param(
            OutcomeCase(
                "unknown",
                "partial",
                {"execution": "unresolved", "mutation": "local-observed"},
            ),
            id="partial-observation",
        ),
    ),
)
def test_opencode_trace_preserves_independent_outcome_axes(
    tmp_path: Path, monkeypatch: MonkeyPatch, case: OutcomeCase
) -> None:
    row = _evaluate_opencode_outcome(tmp_path, monkeypatch, case)

    assert row["execution_outcome"] == case.execution_outcome, (
        "trace must preserve the execution outcome independently"
    )
    assert row["mutation_outcome"] == case.mutation_outcome, (
        "trace must preserve the mutation outcome independently"
    )
    assert row["evidence_tier"] == case.evidence_tier, (
        "trace must preserve evidence tiers for both outcome axes"
    )
    assert row["mutation_outcome"] != "committed", (
        "an OpenCode hook trace must never infer a commit"
    )


def test_opencode_trace_preserves_native_ids_and_raw_after_output(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    case = OutcomeCase(
        "returned",
        "unknown",
        {"execution": "pinned-source", "mutation": "unresolved"},
    )
    row = _evaluate_opencode_outcome(tmp_path, monkeypatch, case)

    assert row["opencode_session_id"] == "session-opencode", (
        "trace must preserve the native OpenCode session ID"
    )
    assert row["call_id"] == "call-opencode", (
        "trace must preserve the native OpenCode call ID"
    )
    assert row["tool_output_raw"] == {"content": "raw after output"}, (
        "trace must retain raw after-hook output for later evidence review"
    )
    assert row["tool_metadata"] == {"source": "opencode"}, (
        "trace must retain typed after-hook metadata"
    )


def test_opencode_trace_exposes_each_owned_timing_phase(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    case = OutcomeCase(
        "returned",
        "unknown",
        {"execution": "pinned-source", "mutation": "unresolved"},
    )
    row = _evaluate_opencode_outcome(tmp_path, monkeypatch, case)
    timing = object_dict(row.get("timing"))

    assert set(timing) == set(_TIMING_PHASES), (
        "result trace should expose exactly the owned evaluation phases"
    )


@pytest.mark.parametrize("phase", _TIMING_PHASES)
def test_opencode_trace_timing_phase_is_non_negative_milliseconds(
    tmp_path: Path, monkeypatch: MonkeyPatch, phase: str
) -> None:
    case = OutcomeCase(
        "returned",
        "unknown",
        {"execution": "pinned-source", "mutation": "unresolved"},
    )
    row = _evaluate_opencode_outcome(tmp_path, monkeypatch, case)
    value = object_dict(row.get("timing"))[phase]

    assert isinstance(value, int) and value >= 0, (
        f"{phase} should be a non-negative integer number of milliseconds"
    )
