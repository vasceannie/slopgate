from __future__ import annotations

from hypothesis import given, strategies

from slopgate.adapters._session_identity import (
    _first_nested_identity_value,
    _identity_object_sources,
)
from tests.test_adapters import CodexAdapter


def test_identity_object_sources_coerces_missing_and_non_object_values() -> None:
    sources = _identity_object_sources(
        {
            "params": {"threadId": "thr_native_codex"},
            "data": "not-an-object",
        },
        ("params", "data", "missing"),
    )

    assert sources == ({"threadId": "thr_native_codex"}, {}, {}), (
        "identity source extraction should preserve object values and coerce non-objects"
    )


def test_first_nested_identity_value_uses_first_trimmed_string() -> None:
    value = _first_nested_identity_value(
        (
            {"threadId": "   "},
            {"conversationId": " thr_native_codex "},
        ),
        ("threadId", "conversationId"),
        metric_name="test.identity.first_value",
    )

    assert value == "thr_native_codex", (
        "identity value lookup should skip blanks and trim the first usable id"
    )


@given(strategies.text())
def test_first_nested_identity_value_trims_all_generated_strings(
    raw_value: str,
) -> None:
    value = _first_nested_identity_value(
        ({"threadId": raw_value},),
        ("threadId",),
        metric_name="test.identity.generated_trim",
    )

    assert value == raw_value.strip(), (
        "identity value lookup should return the stripped generated string or blank"
    )


@given(
    strategies.dictionaries(
        strategies.text(min_size=1),
        strategies.one_of(strategies.text(), strategies.integers()),
    )
)
def test_identity_object_sources_returns_objects_for_generated_mappings(
    generated: dict[str, object],
) -> None:
    sources = _identity_object_sources({"params": generated}, ("params", "missing"))

    assert sources == (generated, {}), (
        "identity source extraction should preserve generated mappings and fill missing keys"
    )


def test_codex_adapter_exercises_shared_identity_helpers_through_real_seam() -> None:
    canonical = CodexAdapter().normalize_payload(
        {
            "method": "thread/started",
            "params": {"thread": {"id": "thr_native_codex", "name": "Named thread"}},
        }
    )

    assert canonical["session_id"] == "thr_native_codex", (
        "real Codex normalization should use shared helper output for session_id"
    )
    assert canonical["session_title"] == "Named thread", (
        "real Codex normalization should use shared helper output for title"
    )
