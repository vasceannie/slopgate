"""Shared canonical payload field extraction for platform adapters."""

from __future__ import annotations

from slopgate._types import ObjectDict, ObjectMapping, string_value
from slopgate.constants import SESSION_ID


def _first_raw_string(raw: ObjectMapping, *keys: str) -> str:
    for key in keys:
        value = string_value(raw.get(key))
        if value:
            return value
    return ""


def merge_session_id(
    raw: ObjectMapping,
    canonical: ObjectDict,
    *,
    extra_keys: tuple[str, ...] = (),
) -> None:
    """Copy session id from common platform key aliases into *canonical*."""
    session_id = _first_raw_string(raw, SESSION_ID, "sessionId", *extra_keys)
    if session_id:
        canonical[SESSION_ID] = session_id


def merge_cwd(
    raw: ObjectMapping,
    canonical: ObjectDict,
    *,
    extra_keys: tuple[str, ...] = (),
) -> None:
    """Copy working-directory hints from *raw* into *canonical*."""
    cwd = _first_raw_string(raw, "cwd", "workspace_root", *extra_keys)
    if cwd:
        canonical["cwd"] = cwd


def merge_standard_session_fields(
    raw: ObjectMapping,
    canonical: ObjectDict,
    *,
    cwd_extra_keys: tuple[str, ...] = (),
) -> None:
    """Populate session id and cwd on *canonical* from common adapter payload keys."""
    merge_session_id(raw, canonical)
    merge_cwd(raw, canonical, extra_keys=cwd_extra_keys)


def sync_tool_result_fields(canonical: ObjectDict, raw: ObjectMapping | None = None) -> None:
    """Align tool_result and tool_response keys on a canonical payload."""
    if raw is not None:
        tool_output = raw.get("tool_output")
        if tool_output is not None:
            if "tool_result" not in canonical:
                canonical["tool_result"] = tool_output
            if "tool_response" not in canonical:
                canonical["tool_response"] = tool_output
    if "tool_response" in canonical and "tool_result" not in canonical:
        canonical["tool_result"] = canonical["tool_response"]
    elif "tool_result" in canonical and "tool_response" not in canonical:
        canonical["tool_response"] = canonical["tool_result"]
    if "tool_output" in canonical and "tool_result" not in canonical:
        canonical["tool_result"] = canonical["tool_output"]
