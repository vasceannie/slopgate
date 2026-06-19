from __future__ import annotations

from hypothesis import given, strategies

from slopgate.adapters._session_identity import (
    first_nested_identity_value,
    identity_object_sources,
)
from slopgate.adapters.codex_identity import CodexSessionIdentity, codex_session_identity
from slopgate.adapters.opencode_identity import (
    OpenCodeSessionIdentity,
    opencode_session_identity,
)
from tests.test_adapters import CodexAdapter


def test_identity_object_sources_coerces_missing_and_non_object_values() -> None:
    sources = identity_object_sources(
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
    value = first_nested_identity_value(
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
    value = first_nested_identity_value(
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
    sources = identity_object_sources({"params": generated}, ("params", "missing"))

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


def test_identity_value_objects_apply_to_canonical_payloads() -> None:
    codex_identity = codex_session_identity(
        {"params": {"thread": {"id": "thread-1", "name": "Named thread"}}}
    )
    opencode_identity = opencode_session_identity(
        {"info": {"id": "session-1", "title": "Named session"}}
    )
    canonical: dict[str, object] = {}

    assert isinstance(codex_identity, CodexSessionIdentity), (
        "codex_session_identity should return the public Codex identity value object"
    )
    assert isinstance(opencode_identity, OpenCodeSessionIdentity), (
        "opencode_session_identity should return the public OpenCode identity value object"
    )
    codex_identity.apply_to(canonical)
    opencode_identity.apply_to(canonical)

    assert canonical["session_id"] == "thread-1", (
        "Codex identity should apply the native thread id as session id"
    )
    assert canonical["session_title"] == "Named thread", (
        "First identity title should remain stable when later identity applies"
    )
    assert canonical["opencode_session_id"] == "session-1", (
        "OpenCode identity should preserve native session id metadata"
    )
