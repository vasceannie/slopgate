"""Codex-native thread identity extraction."""

from __future__ import annotations

from dataclasses import dataclass

from slopgate._types import ObjectDict, ObjectMapping, string_value
from slopgate.adapters._session_identity import (
    SESSION_IDENTITY_TITLE_KEYS,
    SESSION_IDENTITY_TELEMETRY,
    _first_nested_identity_value,
    _identity_object_sources,
)
from slopgate.constants import SESSION_ID

CODEX_DIRECT_THREAD_ID_KEYS = (
    "codex_session_id",
    "codexSessionId",
    "codexSessionID",
    "threadId",
    "threadID",
    "thread_id",
    "conversationId",
    "conversationID",
    "conversation_id",
)
CODEX_THREAD_OBJECT_ID_KEYS = (*CODEX_DIRECT_THREAD_ID_KEYS, "id")
CODEX_DIRECT_THREAD_TITLE_KEYS = (
    *SESSION_IDENTITY_TITLE_KEYS,
    "threadName",
    "thread_name",
)
CODEX_THREAD_OBJECT_TITLE_KEYS = (*CODEX_DIRECT_THREAD_TITLE_KEYS, "name")
CODEX_EVENT_IDENTITY_SOURCE = "codex-thread"


@dataclass(frozen=True, slots=True)
class _CodexSessionIdentity:
    session_id: str
    title: str

    def apply_to(self, canonical: ObjectDict) -> None:
        SESSION_IDENTITY_TELEMETRY.record_metric("codex.identity.apply")
        if self.session_id:
            existing_session_id = string_value(canonical.get(SESSION_ID))
            canonical.setdefault(SESSION_ID, self.session_id)
            canonical.setdefault("codex_session_id", self.session_id)
            canonical.setdefault("session_identity_source", CODEX_EVENT_IDENTITY_SOURCE)
            if existing_session_id and existing_session_id != self.session_id:
                _add_secondary_session_id(canonical, existing_session_id)
        if self.title:
            canonical.setdefault("session_title", self.title)
            canonical.setdefault("session_title_source", CODEX_EVENT_IDENTITY_SOURCE)


def _codex_session_identity(raw: ObjectMapping) -> _CodexSessionIdentity:
    SESSION_IDENTITY_TELEMETRY.record_metric("codex.identity.extract")
    direct_sources, thread_sources, name_params = _identity_sources(raw)
    return _CodexSessionIdentity(
        session_id=_first_nested_identity_value(
            direct_sources,
            CODEX_DIRECT_THREAD_ID_KEYS,
            metric_name="codex.identity.first_value",
        )
        or _first_nested_identity_value(
            thread_sources,
            CODEX_THREAD_OBJECT_ID_KEYS,
            metric_name="codex.identity.thread_value",
        ),
        title=_first_nested_identity_value(
            direct_sources,
            CODEX_DIRECT_THREAD_TITLE_KEYS,
            metric_name="codex.identity.first_title",
        )
        or _first_nested_identity_value(
            thread_sources,
            CODEX_THREAD_OBJECT_TITLE_KEYS,
            metric_name="codex.identity.thread_title",
        )
        or _thread_name_set_value(raw, name_params),
    )


def _identity_sources(
    raw: ObjectMapping,
) -> tuple[tuple[ObjectMapping, ...], tuple[ObjectMapping, ...], ObjectMapping]:
    SESSION_IDENTITY_TELEMETRY.record_metric("codex.identity.sources")
    params, data, result = _identity_object_sources(raw, ("params", "data", "result"))
    return (
        (raw, params, data, result),
        (
            *_identity_object_sources(raw, ("thread",)),
            *_identity_object_sources(params, ("thread",)),
            *_identity_object_sources(data, ("thread",)),
            *_identity_object_sources(result, ("thread",)),
        ),
        params,
    )


def _thread_name_set_value(raw: ObjectMapping, params: ObjectMapping) -> str:
    SESSION_IDENTITY_TELEMETRY.record_metric("codex.identity.thread_name_set")
    method = string_value(raw.get("method"))
    if method != "thread/name/set":
        return ""
    value = string_value(params.get("name"))
    return value.strip() if value and value.strip() else ""


def _add_secondary_session_id(canonical: ObjectDict, session_id: str) -> None:
    SESSION_IDENTITY_TELEMETRY.record_metric("codex.identity.secondary")
    existing = canonical.get("secondary_session_ids")
    if isinstance(existing, list):
        secondary_ids = [item for item in existing if isinstance(item, str)]
    else:
        secondary_ids = []
    if session_id not in secondary_ids:
        secondary_ids.append(session_id)
    canonical["secondary_session_ids"] = secondary_ids
