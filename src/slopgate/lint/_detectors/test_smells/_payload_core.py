"""Detectors for test-specific smells."""

from __future__ import annotations

import ast

from vibeforcer.constants import (
    TEST_PAYLOAD_DEFAULT_THRESHOLD,
    TEST_PAYLOAD_METADATA_THRESHOLD,
    TYPE_NARROWING_GUARD_LINE_WINDOW,
)
from ._assertion_core import _DESERIALIZER_TEST_TOKENS as _DESERIALIZER_TEST_TOKENS, _HIGH_RISK_CAST_TARGET_SUFFIXES as _HIGH_RISK_CAST_TARGET_SUFFIXES, _HIGH_RISK_CAST_TARGET_TOKENS as _HIGH_RISK_CAST_TARGET_TOKENS, _HIGH_RISK_NAMESPACE_KEYS as _HIGH_RISK_NAMESPACE_KEYS, _INTERNAL_SEAM_TOKENS as _INTERNAL_SEAM_TOKENS, _LOW_RISK_CAST_TARGET_TOKENS as _LOW_RISK_CAST_TARGET_TOKENS, _MOCK_FACTORY_NAMES as _MOCK_FACTORY_NAMES, _OUTER_BOUNDARY_PATCH_TOKENS as _OUTER_BOUNDARY_PATCH_TOKENS, _SEMANTIC_MOCK_ASSERTS as _SEMANTIC_MOCK_ASSERTS, _call_tail as _call_tail, _dotted_name as _dotted_name, _is_call_only_mock_assert as _is_call_only_mock_assert, _is_weak_assertion as _is_weak_assertion


def _assigned_names(node: ast.Assign | ast.AnnAssign) -> set[str]:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    names: set[str] = set()
    for target in targets:
        if isinstance(target, ast.Name):
            names.add(target.id.lower())
    return names


def _semantic_assertion_lines(
    test_node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[int]:
    lines: list[int] = []
    for child in ast.walk(test_node):
        if isinstance(child, ast.Call) and _call_tail(child) in _SEMANTIC_MOCK_ASSERTS:
            lines.append(getattr(child, "lineno", test_node.lineno))
            continue
        if not isinstance(child, ast.Assert):
            continue
        if _is_weak_assertion(child) or _is_call_only_mock_assert(child):
            continue
        lines.append(getattr(child, "lineno", test_node.lineno))
    return lines


def _is_type_narrowing_guard(
    weak_node: ast.AST,
    semantic_lines: list[int],
) -> bool:
    """True when a weak assertion is just guarding later semantic checks."""
    if not semantic_lines:
        return False
    weak_line = getattr(weak_node, "lineno", 0)
    return any(0 < weak_line < line <= weak_line + TYPE_NARROWING_GUARD_LINE_WINDOW for line in semantic_lines)


def _cast_target_name(target: ast.AST) -> str:
    if isinstance(target, ast.Subscript):
        return _cast_target_name(target.value)
    return _dotted_name(target)


def _is_low_risk_cast_target(name: str) -> bool:
    parts = [part for dotted in name.split(".") for part in dotted.split("[")]
    return any(part in _LOW_RISK_CAST_TARGET_TOKENS for part in parts)


def _is_high_risk_cast_target(name: str) -> bool:
    if not name or _is_low_risk_cast_target(name):
        return False
    tail = name.rsplit(".", maxsplit=1)[-1]
    return tail in _HIGH_RISK_CAST_TARGET_TOKENS or tail.endswith(_HIGH_RISK_CAST_TARGET_SUFFIXES)


def _test_context_text(path: str, test_name: str) -> str:
    context = f"{path}/{test_name}"
    return context.lower()


def _looks_like_deserializer_contract(path: str, test_name: str) -> bool:
    context = _test_context_text(path, test_name)
    return any(token in context for token in _DESERIALIZER_TEST_TOKENS)


def _dict_payload_threshold(target_names: set[str], path: str, test_name: str) -> int | None:
    if "state" in target_names:
        return 4
    if target_names & {"payload", "event", "response"}:
        if _looks_like_deserializer_contract(path, test_name):
            return None
        return TEST_PAYLOAD_DEFAULT_THRESHOLD
    if "metadata" in target_names:
        return TEST_PAYLOAD_METADATA_THRESHOLD
    if "data" in target_names:
        return TEST_PAYLOAD_DEFAULT_THRESHOLD
    return None


def _string_arg(call: ast.Call) -> str | None:
    if not call.args:
        return None
    first = call.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return None


def _contains_token(text: str, tokens: frozenset[str]) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in tokens)


def _patch_target_is_internal(target: str) -> bool:
    lowered = target.lower()
    if _contains_token(lowered, _OUTER_BOUNDARY_PATCH_TOKENS):
        return False
    return _contains_token(lowered, _INTERNAL_SEAM_TOKENS)


def _mock_name_is_internal(name: str) -> bool:
    lowered = name.lower()
    return lowered in _INTERNAL_SEAM_TOKENS or any(
        token in lowered for token in _INTERNAL_SEAM_TOKENS
    )


def _patch_call_evidence(call: ast.Call) -> str | None:
    tail = _call_tail(call)
    target = _string_arg(call)
    if target is None or not _patch_target_is_internal(target):
        return None
    if tail == "patch":
        return f"line {call.lineno}: patch({target!r})"
    if tail == "setattr":
        return f"line {call.lineno}: monkeypatch/setattr({target!r})"
    return None


def _assignment_mock_evidence(assign: ast.Assign) -> str | None:
    if not isinstance(assign.value, ast.Call):
        return None
    if _call_tail(assign.value) not in _MOCK_FACTORY_NAMES:
        return None
    internal = sorted(name for name in _assigned_names(assign) if _mock_name_is_internal(name))
    if not internal:
        return None
    return f"line {assign.lineno}: internal mock variable {', '.join(internal)}"


def _integration_mock_evidence(test_node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    evidence: list[str] = []
    for child in ast.walk(test_node):
        if isinstance(child, ast.Call):
            call_evidence = _patch_call_evidence(child)
            if call_evidence is not None:
                evidence.append(call_evidence)
        if isinstance(child, ast.Assign):
            assign_evidence = _assignment_mock_evidence(child)
            if assign_evidence is not None:
                evidence.append(assign_evidence)
    return evidence


def _is_high_risk_simple_namespace(call: ast.Call) -> bool:
    keyword_names = {kw.arg for kw in call.keywords if kw.arg is not None}
    return len(keyword_names) >= 2 or bool(keyword_names & _HIGH_RISK_NAMESPACE_KEYS)
