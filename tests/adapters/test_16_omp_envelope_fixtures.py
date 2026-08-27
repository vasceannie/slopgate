from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

import pytest

from slopgate._types import ObjectDict, object_dict
from slopgate.adapters.omp import OmpAdapter
from slopgate.constants import POST_TOOL_USE, PRE_TOOL_USE, SESSION_START, STOP


@dataclass(frozen=True, slots=True)
class EnvelopeExpectation:
    canonical_event: str
    tool_name: str
    stop_response: str | None = None


_FIXTURE_DIR: Final = Path(__file__).parents[1] / "fixtures" / "omp" / "18.0.5"
_EXPECTED_ENVELOPES: Final[dict[str, EnvelopeExpectation]] = {
    "before-agent-start.json": EnvelopeExpectation(SESSION_START, ""),
    "input.json": EnvelopeExpectation("UserPromptSubmit", ""),
    "session-start.json": EnvelopeExpectation(SESSION_START, ""),
    "session-stop-advisory.json": EnvelopeExpectation(
        STOP,
        "",
        "advisory stop response",
    ),
    "session-stop-blocking.json": EnvelopeExpectation(
        STOP,
        "",
        "blocking stop response",
    ),
    "tool-call-bash.json": EnvelopeExpectation(PRE_TOOL_USE, "Bash"),
    "tool-call-write.json": EnvelopeExpectation(PRE_TOOL_USE, "Write"),
    "tool-result-error.json": EnvelopeExpectation("PostToolUseFailure", "Bash"),
    "tool-result-success.json": EnvelopeExpectation(POST_TOOL_USE, "Bash"),
    "turn-end.json": EnvelopeExpectation("TurnEnd", ""),
    "user-bash.json": EnvelopeExpectation(PRE_TOOL_USE, "Bash"),
    "user-python.json": EnvelopeExpectation(PRE_TOOL_USE, "python"),
}
_FIXTURE_PATHS: Final = tuple(sorted(_FIXTURE_DIR.glob("*.json")))
_FIXTURE_IDS: Final = tuple(path.stem for path in _FIXTURE_PATHS)


def _assert_normalized_envelope(
    normalized: ObjectDict,
    expectation: EnvelopeExpectation,
) -> None:
    assert normalized.get("hook_event_name") == expectation.canonical_event, (
        f"expected canonical event {expectation.canonical_event!r}, got {normalized.get('hook_event_name')!r}"
    )
    assert normalized.get("tool_name") == expectation.tool_name, (
        f"expected canonical tool {expectation.tool_name!r}, got {normalized.get('tool_name')!r}"
    )
    assert normalized.get("session_id") == "omp-test-session", (
        f"expected captured session_id, got {normalized.get('session_id')!r}"
    )
    assert normalized.get("cwd") == ".", f"expected captured cwd '.', got {normalized.get('cwd')!r}"
    assert normalized.get("transcript_path") is None, (
        f"expected null transcript_path, got {normalized.get('transcript_path')!r}"
    )
    assert normalized.get("stop_response") == expectation.stop_response, (
        f"expected stop_response {expectation.stop_response!r}, got {normalized.get('stop_response')!r}"
    )


def test_captured_omp_envelope_inventory_is_fully_parameterized() -> None:
    captured_names = {path.name for path in _FIXTURE_PATHS}
    assert captured_names == set(_EXPECTED_ENVELOPES), (
        f"expected fixture cases for every captured envelope; captured={captured_names}, "
        f"expected={set(_EXPECTED_ENVELOPES)}"
    )


@pytest.mark.parametrize("fixture_path", _FIXTURE_PATHS, ids=_FIXTURE_IDS)
def test_captured_omp_envelope_normalizes_contract_fields(fixture_path: Path) -> None:
    raw = object_dict(json.loads(fixture_path.read_text(encoding="utf-8")))

    normalized = OmpAdapter().normalize_payload(raw)

    _assert_normalized_envelope(normalized, _EXPECTED_ENVELOPES[fixture_path.name])


def test_in_memory_envelope_mutation_breaks_contract_assertion() -> None:
    fixture_path = _FIXTURE_DIR / "tool-result-success.json"
    mutated = object_dict(json.loads(fixture_path.read_text(encoding="utf-8")))
    mutated["session_id"] = "mutated-session"

    normalized = OmpAdapter().normalize_payload(mutated)

    with pytest.raises(AssertionError, match="session_id"):
        _assert_normalized_envelope(normalized, _EXPECTED_ENVELOPES[fixture_path.name])
