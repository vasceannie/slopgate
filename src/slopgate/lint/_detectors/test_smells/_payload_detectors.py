"""Detectors for test-specific smells."""

from __future__ import annotations

import ast
from pathlib import Path
from vibeforcer.lint._baseline import Violation
from vibeforcer.lint._helpers import (
    ParsedFile,
    ensure_parsed,
    find_test_files,
)

from ._assertion_core import _INTEGRATION_NAME_TOKENS as _INTEGRATION_NAME_TOKENS, _PAYLOAD_TARGET_NAMES as _PAYLOAD_TARGET_NAMES, _call_tail as _call_tail, _contains_mock_setup as _contains_mock_setup, _expr_preview as _expr_preview, _has_semantic_assertion as _has_semantic_assertion, _is_call_only_mock_assert as _is_call_only_mock_assert, _is_weak_assertion as _is_weak_assertion, _iter_tests as _iter_tests
from ._payload_core import _assigned_names as _assigned_names, _cast_target_name as _cast_target_name, _dict_payload_threshold as _dict_payload_threshold, _integration_mock_evidence as _integration_mock_evidence, _is_high_risk_cast_target as _is_high_risk_cast_target, _is_high_risk_simple_namespace as _is_high_risk_simple_namespace, _is_type_narrowing_guard as _is_type_narrowing_guard, _semantic_assertion_lines as _semantic_assertion_lines


def detect_weak_assertions(
    files: list[Path] | list[ParsedFile] | None = None,
) -> list[Violation]:
    """Find assertions that prove presence/call success instead of behavior."""
    parsed = ensure_parsed(files, fallback=find_test_files())
    violations: list[Violation] = []
    for pf in parsed:
        for test_node in _iter_tests(pf.tree):
            semantic_lines = _semantic_assertion_lines(test_node)
            for child in ast.walk(test_node):
                if not _is_weak_assertion(child):
                    continue
                if _is_type_narrowing_guard(child, semantic_lines):
                    continue
                lineno = getattr(child, "lineno", test_node.lineno)
                violations.append(
                    Violation(
                        rule="weak-test-assertion",
                        relative_path=pf.rel,
                        identifier=f"{test_node.name}:line-{lineno}",
                        detail=f"line {lineno}: {_expr_preview(child)}",
                    )
                )
    return violations


def detect_mock_theater(
    files: list[Path] | list[ParsedFile] | None = None,
) -> list[Violation]:
    """Find tests whose only proof is that a mock was called."""
    parsed = ensure_parsed(files, fallback=find_test_files())
    violations: list[Violation] = []
    for pf in parsed:
        for test_node in _iter_tests(pf.tree):
            if not _contains_mock_setup(test_node):
                continue
            call_only_lines = [
                getattr(child, "lineno", test_node.lineno)
                for child in ast.walk(test_node)
                if _is_call_only_mock_assert(child)
            ]
            if not call_only_lines or _has_semantic_assertion(test_node):
                continue
            violations.append(
                Violation(
                    rule="mock-theater",
                    relative_path=pf.rel,
                    identifier=test_node.name,
                    detail=f"call-only mock assertions at lines {', '.join(str(line) for line in sorted(call_only_lines))}",
                )
            )
    return violations


def _schema_bypass_violation_for_call(
    call: ast.Call,
    pf: ParsedFile,
    test_node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> Violation | None:
    tail = _call_tail(call)
    if tail == "cast" and len(call.args) >= 2 and isinstance(call.args[1], ast.Dict):
        target_name = _cast_target_name(call.args[0])
        if not _is_high_risk_cast_target(target_name):
            return None
        return Violation(
            rule="schema-bypass-test-data",
            relative_path=pf.rel,
            identifier=f"{test_node.name}:line-{call.lineno}",
            detail=f"line {call.lineno}: cast({target_name}, dict literal)",
        )
    if tail == "SimpleNamespace" and call.keywords and _is_high_risk_simple_namespace(call):
        return Violation(
            rule="schema-bypass-test-data",
            relative_path=pf.rel,
            identifier=f"{test_node.name}:line-{call.lineno}",
            detail=f"line {call.lineno}: SimpleNamespace fake model",
        )
    return None


def detect_schema_bypasses(
    files: list[Path] | list[ParsedFile] | None = None,
) -> list[Violation]:
    """Find test data that bypasses real model/schema constructors."""
    parsed = ensure_parsed(files, fallback=find_test_files())
    violations: list[Violation] = []
    for pf in parsed:
        for test_node in _iter_tests(pf.tree):
            for child in ast.walk(test_node):
                if not isinstance(child, ast.Call):
                    continue
                violation = _schema_bypass_violation_for_call(child, pf, test_node)
                if violation is not None:
                    violations.append(violation)
    return violations


def detect_hand_built_test_payloads(
    files: list[Path] | list[ParsedFile] | None = None,
) -> list[Violation]:
    """Find large inline payload/state dicts that can drift from wire schemas."""
    parsed = ensure_parsed(files, fallback=find_test_files())
    violations: list[Violation] = []
    for pf in parsed:
        for test_node in _iter_tests(pf.tree):
            for child in ast.walk(test_node):
                if not isinstance(child, (ast.Assign, ast.AnnAssign)):
                    continue
                value = child.value
                if not isinstance(value, ast.Dict):
                    continue
                target_names = _assigned_names(child)
                if not (target_names & _PAYLOAD_TARGET_NAMES):
                    continue
                threshold = _dict_payload_threshold(target_names, pf.rel, test_node.name)
                if threshold is None or len(value.keys) < threshold:
                    continue
                target_label = next(iter(sorted(target_names & _PAYLOAD_TARGET_NAMES)))
                violations.append(
                    Violation(
                        rule="hand-built-test-payload",
                        relative_path=pf.rel,
                        identifier=f"{test_node.name}:line-{child.lineno}",
                        detail=f"line {child.lineno}: inline {target_label} dict with {len(value.keys)} keys",
                    )
                )
    return violations


def detect_mocked_integration_tests(
    files: list[Path] | list[ParsedFile] | None = None,
) -> list[Violation]:
    """Find e2e/integration/pipeline tests that mock the path under test."""
    parsed = ensure_parsed(files, fallback=find_test_files())
    violations: list[Violation] = []
    for pf in parsed:
        path_text = pf.rel.lower()
        path_claims_integration = any(token in path_text for token in _INTEGRATION_NAME_TOKENS)
        for test_node in _iter_tests(pf.tree):
            name_claims_integration = any(token in test_node.name.lower() for token in _INTEGRATION_NAME_TOKENS)
            if not (path_claims_integration or name_claims_integration):
                continue
            evidence = _integration_mock_evidence(test_node)
            if not evidence:
                continue
            violations.append(
                Violation(
                    rule="mocked-integration-test",
                    relative_path=pf.rel,
                    identifier=test_node.name,
                    detail="; ".join(evidence[:3]),
                )
            )
    return violations
