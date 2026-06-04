from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory
from pathlib import Path

from slopgate._types import ObjectDict, object_dict, string_value
from slopgate.engine import evaluate_payload
from slopgate.models import EngineResult

BUNDLE_ROOT = Path(__file__).resolve().parents[1]


def _assert_denied_by(
    result: EngineResult,
    rule_id: str,
) -> None:
    reason = _permission_reason(result)
    assert _permission_decision(result) == "deny"
    assert rule_id in reason, f"expected {rule_id!r} in reason: {reason!r}"


def _permission_decision(result: EngineResult) -> str | None:
    assert result.output is not None, "expected output, got None"
    spec = object_dict(result.output.get("hookSpecificOutput"))
    decision = string_value(spec.get("permissionDecision"))
    if decision is None:
        inner = object_dict(spec.get("decision"))
        decision = string_value(inner.get("behavior"))
    return decision


def _permission_reason(result: EngineResult) -> str:
    assert result.output is not None, "expected output, got None"
    spec = object_dict(result.output.get("hookSpecificOutput"))
    decision = string_value(spec.get("permissionDecision"))
    if decision is None:
        inner = object_dict(spec.get("decision"))
        return string_value(inner.get("message")) or ""
    else:
        return string_value(spec.get("permissionDecisionReason")) or ""


def _assert_not_denied(result: EngineResult) -> None:
    if result.output is None:
        return
    spec = object_dict(result.output.get("hookSpecificOutput"))
    decision = string_value(spec.get("permissionDecision"))
    assert decision != "deny", f"expected no deny, got {decision!r}"


if __name__ == "__main__":
    _ = unittest.main()

# Exported test support used by split test modules.
__all__ = ('BUNDLE_ROOT', 'EngineResult', 'ObjectDict', 'Path', 'TemporaryDirectory', '_assert_denied_by', '_assert_not_denied', '_permission_decision', '_permission_reason', 'evaluate_payload', 'object_dict', 'string_value', 'unittest')
