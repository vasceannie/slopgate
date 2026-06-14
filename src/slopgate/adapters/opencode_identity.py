"""OpenCode-native session identity extraction."""

from __future__ import annotations

from dataclasses import dataclass

from slopgate._types import ObjectDict, ObjectMapping
from slopgate.adapters._session_identity import (
    SESSION_IDENTITY_TITLE_KEYS,
    SESSION_IDENTITY_TELEMETRY,
    _first_nested_identity_value,
    _identity_object_sources,
)


OPENCODE_DIRECT_SESSION_ID_KEYS = (
    "opencode_session_id",
    "opencodeSessionId",
    "opencodeSessionID",
    "sessionID",
    "sessionId",
    "aggregate_id",
    "aggregateId",
)
OPENCODE_INFO_SESSION_ID_KEYS = (*OPENCODE_DIRECT_SESSION_ID_KEYS, "id")
OPENCODE_DIRECT_SESSION_TITLE_KEYS = SESSION_IDENTITY_TITLE_KEYS
OPENCODE_INFO_SESSION_TITLE_KEYS = (*OPENCODE_DIRECT_SESSION_TITLE_KEYS, "title")
OPENCODE_EVENT_IDENTITY_SOURCE = "opencode-event"


@dataclass(frozen=True, slots=True)
class _OpenCodeSessionIdentity:
    session_id: str
    title: str

    def apply_to(self, canonical: ObjectDict) -> None:
        SESSION_IDENTITY_TELEMETRY.record_metric("opencode.identity.apply")
        if self.session_id:
            canonical.setdefault("opencode_session_id", self.session_id)
            canonical.setdefault(
                "session_identity_source", OPENCODE_EVENT_IDENTITY_SOURCE
            )
        if self.title:
            canonical.setdefault("session_title", self.title)
            canonical.setdefault("session_title_source", OPENCODE_EVENT_IDENTITY_SOURCE)


def _opencode_session_identity(raw: ObjectMapping) -> _OpenCodeSessionIdentity:
    SESSION_IDENTITY_TELEMETRY.record_metric("opencode.identity.extract")
    direct_sources, info_sources = _identity_sources(raw)
    return _OpenCodeSessionIdentity(
        session_id=_first_nested_identity_value(
            direct_sources,
            OPENCODE_DIRECT_SESSION_ID_KEYS,
            metric_name="opencode.identity.first_value",
        )
        or _first_nested_identity_value(
            info_sources,
            OPENCODE_INFO_SESSION_ID_KEYS,
            metric_name="opencode.identity.info_value",
        ),
        title=_first_nested_identity_value(
            direct_sources,
            OPENCODE_DIRECT_SESSION_TITLE_KEYS,
            metric_name="opencode.identity.first_title",
        )
        or _first_nested_identity_value(
            info_sources,
            OPENCODE_INFO_SESSION_TITLE_KEYS,
            metric_name="opencode.identity.info_title",
        ),
    )


def _identity_sources(raw: ObjectMapping) -> tuple[tuple[ObjectMapping, ...], ...]:
    SESSION_IDENTITY_TELEMETRY.record_metric("opencode.identity.sources")
    properties, data = _identity_object_sources(raw, ("properties", "data"))
    return (
        (raw, properties, data),
        (
            *_identity_object_sources(raw, ("info",)),
            *_identity_object_sources(properties, ("info",)),
            *_identity_object_sources(data, ("info",)),
        ),
    )
