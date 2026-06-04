"""Property tests for shared adapter payload field helpers."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies

from slopgate._types import object_dict
from slopgate.adapters._payload_fields import (
    merge_cwd,
    merge_session_id,
    merge_standard_session_fields,
    sync_tool_result_fields,
)
from slopgate.constants import SESSION_ID

_NON_BLANK_TEXT = strategies.text(min_size=1, max_size=64).filter(
    lambda value: value.strip() != ""
)


@given(session_id=_NON_BLANK_TEXT)
def test_merge_session_id_copies_session_id_alias(session_id: str) -> None:
    raw = {"sessionId": session_id}
    canonical = object_dict({})
    merge_session_id(raw, canonical)
    assert canonical[SESSION_ID] == session_id


@given(cwd=_NON_BLANK_TEXT)
def test_merge_cwd_copies_workspace_root(cwd: str) -> None:
    raw = {"workspace_root": cwd}
    canonical = object_dict({})
    merge_cwd(raw, canonical)
    assert canonical["cwd"] == cwd


@given(session_id=_NON_BLANK_TEXT, cwd=_NON_BLANK_TEXT)
def test_merge_standard_session_fields_composes_session_and_cwd(
    session_id: str,
    cwd: str,
) -> None:
    raw = {"session_id": session_id, "workspace_root": cwd}
    canonical = object_dict({})
    merge_standard_session_fields(raw, canonical)
    assert canonical[SESSION_ID] == session_id
    assert canonical["cwd"] == cwd


@given(
    payload=strategies.fixed_dictionaries(
        {
            "tool_response": strategies.fixed_dictionaries({"ok": strategies.booleans()}),
        }
    ),
)
def test_sync_tool_result_fields_mirrors_response(payload: dict[str, object]) -> None:
    canonical = object_dict(dict(payload))
    sync_tool_result_fields(canonical)
    assert canonical["tool_result"] == canonical["tool_response"]
