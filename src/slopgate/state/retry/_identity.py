"""Parsing and comparison for semantic retry identities."""

from __future__ import annotations

import json
import re

from slopgate._types import object_dict, string_value
from slopgate.constants import METADATA_PATH, SESSION_ID

from .._models import SemanticRetryKey


_DESIGN_TOKEN = re.compile(r"[a-z0-9]+")


def parse_semantic_key(raw: str) -> SemanticRetryKey | None:
    try:
        parsed = object_dict(json.loads(raw))
    except json.JSONDecodeError:
        return None
    session_id = string_value(parsed.get(SESSION_ID))
    repo_root = string_value(parsed.get("repo_root"))
    rule_id = string_value(parsed.get("rule_id"))
    if session_id is None or repo_root is None or rule_id is None:
        return None
    return SemanticRetryKey(
        session_id=session_id,
        repo_root=repo_root,
        rule_id=rule_id,
        path=string_value(parsed.get(METADATA_PATH)),
        operation_category=string_value(parsed.get("operation_category")),
    )


def materially_different_design(previous: str, new: str) -> bool:
    previous_tokens = set(_DESIGN_TOKEN.findall(previous.casefold()))
    new_tokens = set(_DESIGN_TOKEN.findall(new.casefold()))
    if not previous_tokens or not new_tokens:
        return False
    overlap = len(previous_tokens & new_tokens) / len(previous_tokens | new_tokens)
    return overlap < 0.8
