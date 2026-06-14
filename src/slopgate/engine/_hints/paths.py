from __future__ import annotations

from slopgate.models import RuleFinding
from slopgate.util.metadata_paths import effective_metadata_path


def is_test_path(path_value: str | None) -> bool:
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


def finding_path(item: RuleFinding) -> str | None:
    metadata = item.metadata
    return effective_metadata_path(metadata)
