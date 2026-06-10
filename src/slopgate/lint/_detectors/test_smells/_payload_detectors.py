"""Detectors for test-specific smells."""

from __future__ import annotations
import ast
from pathlib import Path
from slopgate.lint._baseline import Violation
from slopgate.lint._helpers import ParsedFile, ensure_parsed, find_test_files
from ._assertion_core import (
    INTEGRATION_NAME_TOKENS,
    PAYLOAD_TARGET_NAMES,
    call_tail,
    contains_mock_setup,
    expr_preview,
    has_semantic_assertion,
    is_call_only_mock_assert,
    is_weak_assertion,
    iter_tests,
)
from ._payload_core import (
    assigned_names,
    cast_target_name,
    dict_payload_threshold,
    integration_mock_evidence,
    is_high_risk_cast_target,
    is_high_risk_simple_namespace,
    is_type_narrowing_guard,
    semantic_assertion_lines,
)


def detect_weak_assertions(
    files: list[Path] | list[ParsedFile] | None = None,
) -> list[Violation]:
    """Find assertions that prove presence/call success instead of behavior."""
    parsed = ensure_parsed(files, fallback=find_test_files())
    violations: list[Violation] = []
    for pf in parsed:
        for test_node in iter_tests(pf.tree):
            semantic_lines = semantic_assertion_lines(test_node)
            for child in ast.walk(test_node):
                if not is_weak_assertion(child):
                    continue
                if is_type_narrowing_guard(child, semantic_lines):
                    continue
                lineno = getattr(child, "lineno", test_node.lineno)
                violations.append(
                    Violation(
                        rule="weak-test-assertion",
                        relative_path=pf.rel,
                        identifier=f"{test_node.name}:line-{lineno}",
                        detail=f"line {lineno}: {expr_preview(child)}",
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
        for test_node in iter_tests(pf.tree):
            if not contains_mock_setup(test_node):
                continue
            call_only_lines = [
                getattr(child, "lineno", test_node.lineno)
                for child in ast.walk(test_node)
                if is_call_only_mock_assert(child)
            ]
            if not call_only_lines or has_semantic_assertion(test_node):
                continue
            violations.append(
                Violation(
                    rule="mock-theater",
                    relative_path=pf.rel,
                    identifier=test_node.name,
                    detail=f"call-only mock assertions at lines {', '.join((str(line) for line in sorted(call_only_lines)))}",
                )
            )
    return violations


def schema_bypass_violation_for_call(
    call: ast.Call, pf: ParsedFile, test_node: ast.FunctionDef | ast.AsyncFunctionDef
) -> Violation | None:
    tail = call_tail(call)
    if tail == "cast" and len(call.args) >= 2 and isinstance(call.args[1], ast.Dict):
        target_name = cast_target_name(call.args[0])
        if not is_high_risk_cast_target(target_name):
            return None
        return Violation(
            rule="schema-bypass-test-data",
            relative_path=pf.rel,
            identifier=f"{test_node.name}:line-{call.lineno}",
            detail=f"line {call.lineno}: cast({target_name}, dict literal)",
        )
    if (
        tail == "SimpleNamespace"
        and call.keywords
        and is_high_risk_simple_namespace(call)
    ):
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
        for test_node in iter_tests(pf.tree):
            for child in ast.walk(test_node):
                if not isinstance(child, ast.Call):
                    continue
                violation = schema_bypass_violation_for_call(child, pf, test_node)
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
        for test_node in iter_tests(pf.tree):
            for child in ast.walk(test_node):
                if not isinstance(child, (ast.Assign, ast.AnnAssign)):
                    continue
                value = child.value
                if not isinstance(value, ast.Dict):
                    continue
                target_names = assigned_names(child)
                if not target_names & PAYLOAD_TARGET_NAMES:
                    continue
                threshold = dict_payload_threshold(target_names, pf.rel, test_node.name)
                if threshold is None or len(value.keys) < threshold:
                    continue
                target_label = next(iter(sorted(target_names & PAYLOAD_TARGET_NAMES)))
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
        path_claims_integration = any(
            (token in path_text for token in INTEGRATION_NAME_TOKENS)
        )
        for test_node in iter_tests(pf.tree):
            name_claims_integration = any(
                (token in test_node.name.lower() for token in INTEGRATION_NAME_TOKENS)
            )
            if not (path_claims_integration or name_claims_integration):
                continue
            evidence = integration_mock_evidence(test_node)
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
