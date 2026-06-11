from __future__ import annotations

from slopgate._types import object_dict, object_list, string_value
from slopgate.constants import METADATA_PATH
from slopgate.models import RuleFinding
from slopgate.util.path_filters import is_third_party_or_virtualenv_path


def _is_test_path(path_value: str | None) -> bool:
    if path_value is None:
        return False
    normalized = path_value.replace("\\", "/")
    return normalized.startswith("tests/") or "/tests/" in normalized


def failure_class(rule_id: str) -> str:
    if rule_id.startswith("PY-CODE") or rule_id.startswith("PY-QUALITY"):
        return "structural" if rule_id.startswith("PY-CODE") else "quality"
    if "SHELL" in rule_id or rule_id.startswith("GIT-"):
        return "policy_tooling"
    return "quality"


def _quality_display_path(path_value: str | None) -> str | None:
    if not path_value:
        return None
    normalized = path_value.replace("\\", "/")
    lowered = normalized.lower()
    if lowered in {"content", "patch.diff"}:
        return None
    if is_third_party_or_virtualenv_path(normalized):
        return None
    return path_value


def _first_hit_path(item: RuleFinding) -> str | None:
    for hit in object_list(item.metadata.get("hits")):
        if isinstance(hit, str) and hit and hit != "content":
            display_path = _quality_display_path(hit)
            if display_path:
                return display_path
        hit_path = string_value(object_dict(hit).get(METADATA_PATH))
        display_path = _quality_display_path(hit_path)
        if display_path:
            return display_path
    return None


def finding_path(item: RuleFinding) -> str | None:
    path = item.metadata.get(METADATA_PATH)
    if isinstance(path, str) and path:
        display_path = _quality_display_path(path)
        if display_path is None:
            return _first_hit_path(item)
        return display_path
    return None
