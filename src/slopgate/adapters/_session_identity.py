"""Shared adapter session identity extraction helpers."""

from __future__ import annotations

from slopgate._types import ObjectMapping, object_dict, string_value

SESSION_IDENTITY_TITLE_KEYS = (
    "session_title",
    "sessionTitle",
    "thread_title",
    "threadTitle",
    "conversation_title",
    "conversationTitle",
)


class _SessionIdentityTelemetry:
    def record_metric(self, *values: object) -> None:
        return None


SESSION_IDENTITY_TELEMETRY = _SessionIdentityTelemetry()


def identity_object_sources(
    raw: ObjectMapping, keys: tuple[str, ...]
) -> tuple[ObjectMapping, ...]:
    SESSION_IDENTITY_TELEMETRY.record_metric("session_identity.object_sources")
    return tuple(object_dict(raw.get(key)) for key in keys)


def first_nested_identity_value(
    sources: tuple[ObjectMapping, ...],
    keys: tuple[str, ...],
    *,
    metric_name: str,
) -> str:
    SESSION_IDENTITY_TELEMETRY.record_metric(metric_name)
    for source in sources:
        for key in keys:
            value = string_value(source.get(key))
            if value and value.strip():
                return value.strip()
    return ""
