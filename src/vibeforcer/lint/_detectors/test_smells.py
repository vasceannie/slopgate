"""Detectors for test-specific smells.

Long tests, eager tests (too many SUT calls), assertion-free tests,
assertion roulette, conditional assertions, fixtures outside conftest.
"""
from __future__ import annotations

import ast
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from vibeforcer._types import ObjectDict
from vibeforcer.lint._baseline import Violation
from vibeforcer.lint._config import get_config
from vibeforcer.lint._helpers import (
    ParsedFile,
    ensure_parsed,
    find_test_files,
    function_body_lines,
    relative_path,
    safe_parse,
)


# ---------------------------------------------------------------------------
# Long tests
# ---------------------------------------------------------------------------

def detect_long_tests(files: list[Path] | None = None) -> list[Violation]:
    """Find test functions/methods exceeding the configured line-count limit."""
    cfg = get_config()
    files = files if files is not None else find_test_files()
    violations: list[Violation] = []
    for path in files:
        tree = safe_parse(path)
        if tree is None:
            continue
        rel = relative_path(path)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("test_"):
                    continue
                lines = function_body_lines(node)
                if lines > cfg.max_test_lines:
                    violations.append(
                        Violation(
                            rule="long-test",
                            relative_path=rel,
                            identifier=node.name,
                            detail=f"lines={lines}",
                        )
                    )
    return violations


# ---------------------------------------------------------------------------
# Eager tests — too many calls to the SUT in a single test
# ---------------------------------------------------------------------------

def _count_sut_calls(node: ast.AST) -> int:
    """Count non-assert function/method calls in a test body.

    Excludes common setup helpers (``mock``, ``patch``, ``fixture``,
    ``print``, ``len``, ``list``, ``dict``, ``set``, ``str``, ``int``,
    ``isinstance``, ``type``, ``getattr``, ``setattr``, ``hasattr``).
    """
    _IGNORED = frozenset({
        "mock", "patch", "fixture", "print", "len", "list", "dict",
        "set", "str", "int", "float", "tuple", "bool", "bytes",
        "isinstance", "type", "getattr", "setattr", "hasattr",
        "sorted", "reversed", "enumerate", "range", "zip", "map",
        "filter", "any", "all", "min", "max", "sum", "round",
        "repr", "id", "vars", "dir", "super",
    })
    count = 0
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        name = ""
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        if name.startswith("assert"):
            continue
        if name.lower() in _IGNORED:
            continue
        count += 1
    return count


def detect_eager_tests(files: list[Path] | None = None) -> list[Violation]:
    """Find test functions with too many SUT calls."""
    cfg = get_config()
    files = files if files is not None else find_test_files()
    violations: list[Violation] = []
    for path in files:
        tree = safe_parse(path)
        if tree is None:
            continue
        rel = relative_path(path)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("test_"):
                    continue
                calls = _count_sut_calls(node)
                if calls > cfg.max_eager_test_calls:
                    violations.append(
                        Violation(
                            rule="eager-test",
                            relative_path=rel,
                            identifier=node.name,
                            detail=f"sut_calls={calls}",
                        )
                    )
    return violations


# ---------------------------------------------------------------------------
# Assertion-free tests
# ---------------------------------------------------------------------------

_ASSERT_PATTERNS = frozenset({
    "assert", "assertEqual", "assertRaises", "assertIn",
    "assertTrue", "assertFalse", "assertIsNone", "assertIsNotNone",
    "assertAlmostEqual", "assertGreater", "assertLess",
    "assertRegex", "assertNotEqual", "assertIs",
    "assert_called", "assert_called_once", "assert_called_with",
    "assert_called_once_with", "assert_not_called",
    "assert_any_call", "assert_has_calls",
})


def _has_assertion(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Check whether a test function contains at least one assertion."""
    for child in ast.walk(node):
        # bare assert statement
        if isinstance(child, ast.Assert):
            return True
        # pytest.raises / unittest assertX / mock assert_*
        if isinstance(child, ast.Call):
            func = child.func
            name = ""
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name in _ASSERT_PATTERNS:
                return True
        # ``with pytest.raises(...)``
        if isinstance(child, ast.With):
            for item in child.items:
                if isinstance(item.context_expr, ast.Call):
                    call_func = item.context_expr.func
                    if isinstance(call_func, ast.Attribute) and call_func.attr == "raises":
                        return True
    return False


def detect_assertion_free_tests(files: list[Path] | None = None) -> list[Violation]:
    """Find test functions that never assert anything."""
    files = files if files is not None else find_test_files()
    violations: list[Violation] = []
    for path in files:
        tree = safe_parse(path)
        if tree is None:
            continue
        rel = relative_path(path)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("test_"):
                    continue
                if not _has_assertion(node):
                    violations.append(
                        Violation(
                            rule="assertion-free-test",
                            relative_path=rel,
                            identifier=node.name,
                        )
                    )
    return violations


# ---------------------------------------------------------------------------
# Assertion roulette — too many bare asserts in a row
# ---------------------------------------------------------------------------

def _is_bare_assert(node: ast.stmt) -> bool:
    """True when *node* is an ``assert`` statement without a message."""
    return isinstance(node, ast.Assert) and node.msg is None


def _max_bare_assert_run(stmts: list[ast.stmt]) -> int:
    """Return the longest run of consecutive bare asserts in *stmts*.

    Recurses into ``with`` blocks so that bare asserts inside
    ``with pytest.raises(...)`` or other context managers are counted.
    """
    run = 0
    best = 0
    for stmt in stmts:
        if _is_bare_assert(stmt):
            run += 1
            if run > best:
                best = run
        else:
            run = 0
            # Recurse into with-block bodies
            if isinstance(stmt, ast.With):
                nested = _max_bare_assert_run(stmt.body)
                if nested > best:
                    best = nested
    return best


def detect_assertion_roulette(
    files: list[Path] | list[ParsedFile] | None = None,
) -> list[Violation]:
    """Find test functions with long runs of bare ``assert`` (no message).

    Flags when more than ``cfg.max_consecutive_bare_asserts`` consecutive
    bare asserts appear in a test function body (including inside ``with``
    blocks).
    """
    cfg = get_config()
    threshold = cfg.max_consecutive_bare_asserts
    parsed = ensure_parsed(files, fallback=find_test_files())
    violations: list[Violation] = []

    for pf in parsed:
        for node in ast.walk(pf.tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith("test_"):
                continue
            max_run = _max_bare_assert_run(node.body)
            if max_run > threshold:
                violations.append(
                    Violation(
                        rule="assertion-roulette",
                        relative_path=pf.rel,
                        identifier=node.name,
                        detail=f"consecutive_bare_asserts={max_run}",
                    )
                )
    return violations


# ---------------------------------------------------------------------------
# Conditional assertions — asserts inside if/for/while
# ---------------------------------------------------------------------------

def _contains_assert(node: ast.AST) -> bool:
    """True if the subtree rooted at *node* contains any assertion."""
    for child in ast.walk(node):
        if isinstance(child, ast.Assert):
            return True
        if isinstance(child, ast.Call):
            func = child.func
            name = ""
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name in _ASSERT_PATTERNS:
                return True
    return False


def detect_conditional_assertions(
    files: list[Path] | list[ParsedFile] | None = None,
) -> list[Violation]:
    """Find test functions with assertions inside ``if``/``for``/``while``."""
    cfg = get_config()
    if not cfg.ban_conditional_assertions:
        return []

    parsed = ensure_parsed(files, fallback=find_test_files())
    violations: list[Violation] = []

    for pf in parsed:
        for node in ast.walk(pf.tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith("test_"):
                continue
            for child in ast.walk(node):
                if isinstance(child, (ast.For, ast.While, ast.If)):
                    if _contains_assert(child):
                        violations.append(
                            Violation(
                                rule="conditional-assertion",
                                relative_path=pf.rel,
                                identifier=node.name,
                                detail=f"line {child.lineno}",
                            )
                        )
                        break  # one per function
    return violations


# ---------------------------------------------------------------------------
# Fixtures outside conftest.py
# ---------------------------------------------------------------------------

def _is_pytest_fixture_decorator(dec: ast.expr) -> bool:
    """True if *dec* looks like ``@pytest.fixture``, ``@pytest.fixture(...)``,
    or ``@fixture`` / ``@fixture(...)`` (when imported directly).
    """
    # @pytest.fixture
    if isinstance(dec, ast.Attribute):
        return (
            dec.attr == "fixture"
            and isinstance(dec.value, ast.Name)
            and dec.value.id == "pytest"
        )
    # @fixture  (from pytest import fixture)
    if isinstance(dec, ast.Name):
        return dec.id == "fixture"
    # @pytest.fixture(...) or @fixture(...)
    if isinstance(dec, ast.Call):
        return _is_pytest_fixture_decorator(dec.func)
    return False


def _is_fixture_support_module(path: Path) -> bool:
    """True for dedicated test fixture/support implementation modules."""
    normalized_parts = tuple(part.lower() for part in path.parts)
    return "_fixtures" in normalized_parts or "support" in normalized_parts


def detect_fixtures_outside_conftest(
    files: list[Path] | list[ParsedFile] | None = None,
) -> list[Violation]:
    """Find inline ``@pytest.fixture`` definitions in actual test modules.

    ``conftest.py`` remains the public pytest fixture registry. Dedicated
    support modules such as ``tests/<area>/_fixtures/*.py`` and
    ``tests/<area>/support/*.py`` may hold implementation-heavy fixtures so
    large test suites do not have to choose between this rule and module-size
    limits.
    """
    cfg = get_config()
    if not cfg.ban_fixtures_outside_conftest:
        return []

    parsed = ensure_parsed(files, fallback=find_test_files())
    violations: list[Violation] = []

    for pf in parsed:
        if pf.path.name == "conftest.py" or _is_fixture_support_module(pf.path):
            continue
        for node in ast.walk(pf.tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                if _is_pytest_fixture_decorator(dec):
                    violations.append(
                        Violation(
                            rule="fixture-outside-conftest",
                            relative_path=pf.rel,
                            identifier=node.name,
                            detail=f"line {node.lineno}",
                        )
                    )
                    break
    return violations


# ---------------------------------------------------------------------------
# Test integrity — weak assertions, mock theater, and schema bypasses
# ---------------------------------------------------------------------------

_WEAK_ASSERT_NAMES = frozenset({"assertTrue", "assertIsNotNone"})
_MOCK_FACTORY_NAMES = frozenset({"Mock", "MagicMock", "AsyncMock"})
_MOCK_SETUP_NAMES = frozenset({"patch", "setattr"})
_CALL_ONLY_MOCK_ASSERTS = frozenset({
    "assert_called",
    "assert_called_once",
})
_SEMANTIC_MOCK_ASSERTS = frozenset({
    "assert_called_with",
    "assert_called_once_with",
    "assert_any_call",
    "assert_has_calls",
})
_INTEGRATION_NAME_TOKENS = ("e2e", "end_to_end", "integration", "pipeline")
_PAYLOAD_TARGET_NAMES = frozenset({
    "data",
    "event",
    "metadata",
    "payload",
    "response",
    "state",
})
_WEAK_TRUTHY_NAMES = _PAYLOAD_TARGET_NAMES | {"success", "ok", "result"}
_LOW_RISK_CAST_TARGET_TOKENS = frozenset({
    "Any",
    "Dict",
    "Iterable",
    "JsonArray",
    "JsonObject",
    "JsonValue",
    "List",
    "Mapping",
    "MutableMapping",
    "MutableSequence",
    "Sequence",
    "TypedDict",
    "dict",
    "list",
    "object",
    "set",
    "tuple",
})
_HIGH_RISK_CAST_TARGET_SUFFIXES = (
    "Config",
    "Metadata",
    "Model",
    "Result",
    "Snapshot",
    "State",
)
_HIGH_RISK_CAST_TARGET_TOKENS = frozenset({
    "DetectionResult",
    "ExecutorGraphState",
    "GraphState",
    "JudgeGraphState",
    "JobMetadata",
    "OrchestrationState",
    "PlannerGraphState",
})
_DESERIALIZER_TEST_TOKENS = (
    "contract",
    "deserialize",
    "deserializer",
    "malformed",
    "parse",
    "parser",
    "schema",
    "unknown_fields",
    "wire",
)
_INTERNAL_SEAM_TOKENS = frozenset({
    "client",
    "enrich",
    "enrichment",
    "event_handler",
    "handler",
    "parser",
    "projection",
    "renderer",
    "screen",
    "serializer",
    "store",
    "widget",
})
_OUTER_BOUNDARY_PATCH_TOKENS = frozenset({
    "api",
    "bootstrap",
    "client_session",
    "datetime",
    "environ",
    "envvar",
    "external",
    "http",
    "module",
    "os.environ",
    "planner",
    "random",
    "requests",
    "subprocess",
    "sys.modules",
    "tempfile",
    "time",
    "uuid",
})
_HIGH_RISK_NAMESPACE_KEYS = frozenset({
    "company",
    "control_id",
    "field",
    "fields",
    "job_metadata",
    "metadata",
    "payload",
    "snapshot",
    "state",
})


def _dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _call_tail(call: ast.Call) -> str:
    return _dotted_name(call.func).rsplit(".", maxsplit=1)[-1]


def _iter_tests(tree: ast.AST) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    ]


def _is_none_constant(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def _is_true_constant(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def _is_zero_constant(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value == 0


def _is_len_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "len"
    )


def _is_weak_compare(compare: ast.Compare) -> bool:
    if not compare.ops or not compare.comparators:
        return False
    right = compare.comparators[0]
    op = compare.ops[0]
    if isinstance(op, (ast.IsNot, ast.NotEq)) and _is_none_constant(right):
        return True
    if isinstance(op, ast.Is) and _is_true_constant(right):
        return True
    return _is_len_call(compare.left) and isinstance(op, (ast.Gt, ast.NotEq)) and _is_zero_constant(right)


def _is_call_only_mock_assert(node: ast.AST) -> bool:
    if isinstance(node, ast.Call) and _call_tail(node) in _CALL_ONLY_MOCK_ASSERTS:
        return True
    if not isinstance(node, ast.Assert):
        return False
    test = node.test
    if isinstance(test, ast.Attribute):
        return test.attr == "called"
    if isinstance(test, ast.Compare) and isinstance(test.left, ast.Attribute):
        return test.left.attr == "call_count"
    return False


def _is_weak_assertion(node: ast.AST) -> bool:
    if isinstance(node, ast.Assert):
        test = node.test
        if isinstance(test, ast.Compare):
            return _is_weak_compare(test)
        if isinstance(test, ast.Name) and test.id.lower() in _WEAK_TRUTHY_NAMES:
            return True
        if isinstance(test, ast.Call) and _is_len_call(test):
            return True
    if isinstance(node, ast.Call):
        tail = _call_tail(node)
        if tail in _WEAK_ASSERT_NAMES:
            return True
    return False


def _contains_mock_setup(node: ast.AST) -> bool:
    for child in ast.walk(node):
        if not isinstance(child, ast.Call):
            continue
        name = _dotted_name(child.func)
        tail = name.rsplit(".", maxsplit=1)[-1]
        if tail in _MOCK_FACTORY_NAMES:
            return True
        if tail in _MOCK_SETUP_NAMES and (tail == "patch" or name.startswith("monkeypatch.")):
            return True
    return False


def _has_semantic_assertion(test_node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for child in ast.walk(test_node):
        if isinstance(child, ast.Call) and _call_tail(child) in _SEMANTIC_MOCK_ASSERTS:
            return True
        if isinstance(child, ast.Assert):
            if _is_weak_assertion(child) or _is_call_only_mock_assert(child):
                continue
            return True
    return False


def _expr_preview(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return type(node).__name__


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
    return any(0 < weak_line < line <= weak_line + 8 for line in semantic_lines)


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
    return f"{path}/{test_name}".lower()


def _looks_like_deserializer_contract(path: str, test_name: str) -> bool:
    context = _test_context_text(path, test_name)
    return any(token in context for token in _DESERIALIZER_TEST_TOKENS)


def _dict_payload_threshold(target_names: set[str], path: str, test_name: str) -> int | None:
    if "state" in target_names:
        return 4
    if target_names & {"payload", "event", "response"}:
        if _looks_like_deserializer_contract(path, test_name):
            return None
        return 8
    if "metadata" in target_names:
        return 6
    if "data" in target_names:
        return 8
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


def _integration_mock_evidence(test_node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    evidence: list[str] = []
    for child in ast.walk(test_node):
        if isinstance(child, ast.Call):
            tail = _call_tail(child)
            target = _string_arg(child)
            if tail == "patch" and target and _patch_target_is_internal(target):
                evidence.append(f"line {child.lineno}: patch({target!r})")
            elif tail == "setattr" and target and _patch_target_is_internal(target):
                evidence.append(f"line {child.lineno}: monkeypatch/setattr({target!r})")
        if isinstance(child, ast.Assign) and isinstance(child.value, ast.Call):
            if _call_tail(child.value) not in _MOCK_FACTORY_NAMES:
                continue
            names = _assigned_names(child)
            internal = sorted(name for name in names if _mock_name_is_internal(name))
            if internal:
                evidence.append(
                    f"line {child.lineno}: internal mock variable {', '.join(internal)}"
                )
    return evidence


def _is_high_risk_simple_namespace(call: ast.Call) -> bool:
    keyword_names = {kw.arg for kw in call.keywords if kw.arg is not None}
    return len(keyword_names) >= 2 or bool(keyword_names & _HIGH_RISK_NAMESPACE_KEYS)


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
                tail = _call_tail(child)
                if tail == "cast" and len(child.args) >= 2 and isinstance(child.args[1], ast.Dict):
                    target_name = _cast_target_name(child.args[0])
                    if not _is_high_risk_cast_target(target_name):
                        continue
                    violations.append(
                        Violation(
                            rule="schema-bypass-test-data",
                            relative_path=pf.rel,
                            identifier=f"{test_node.name}:line-{child.lineno}",
                            detail=f"line {child.lineno}: cast({target_name}, dict literal)",
                        )
                    )
                elif tail == "SimpleNamespace" and child.keywords and _is_high_risk_simple_namespace(child):
                    violations.append(
                        Violation(
                            rule="schema-bypass-test-data",
                            relative_path=pf.rel,
                            identifier=f"{test_node.name}:line-{child.lineno}",
                            detail=f"line {child.lineno}: SimpleNamespace fake model",
                        )
                    )
    return violations


def _assigned_names(node: ast.Assign | ast.AnnAssign) -> set[str]:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    names: set[str] = set()
    for target in targets:
        if isinstance(target, ast.Name):
            names.add(target.id.lower())
    return names


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


# ---------------------------------------------------------------------------
# Test integrity — holistic suite coverage / seam / property-test signals
# ---------------------------------------------------------------------------

_HYPOTHESIS_NAME_TOKENS = (
    "bound",
    "coerce",
    "dedupe",
    "extract",
    "filter",
    "format",
    "merge",
    "normalize",
    "parse",
    "rank",
    "score",
    "serialize",
    "sort",
    "validate",
)
_DEPRECATED_TOKENS = ("deprecated", "deprecationwarning", "legacy", "obsolete")
_INTEGRATION_HELPER_NAME_PREFIXES = ("as_", "get_", "is_", "to_")
_INTEGRATION_UTILITY_NAME_TOKENS = {
    "color",
    "colors",
    "icon",
    "icons",
    "label",
    "labels",
    "markup",
    "style",
    "styles",
    "title",
}
_INTEGRATION_UTILITY_MODULE_TOKENS = {
    ".colors",
    ".constants",
    ".icons",
    ".labels",
    ".markup",
    ".styles",
    ".theme",
    ".themes",
    ".types",
    ".typing",
    ".utils",
}
_INTEGRATION_SEAM_TOKENS = {
    "adapter",
    "api",
    "client",
    "command",
    "controller",
    "deserialize",
    "enrich",
    "error",
    "event",
    "graph",
    "handler",
    "orchestrat",
    "parse",
    "persist",
    "pipeline",
    "planner",
    "projection",
    "render",
    "repository",
    "route",
    "router",
    "screen",
    "seam",
    "serialize",
    "service",
    "sse",
    "store",
    "stream",
    "sync",
    "workflow",
}
_COVERAGE_JSON_NAMES = ("coverage.json", ".coverage.json")
_COVERAGE_XML_NAMES = ("coverage.xml", ".coverage.xml")
_REPLACEMENT_PATTERNS = (
    re.compile(r"use\s+([A-Za-z_][\w.]+)\s+instead", re.IGNORECASE),
    re.compile(r"replaced\s+by\s+([A-Za-z_][\w.]+)", re.IGNORECASE),
    re.compile(r"migrate\s+to\s+([A-Za-z_][\w.]+)", re.IGNORECASE),
)


@dataclass(frozen=True)
class _ProductionSymbol:
    name: str
    qualname: str
    module: str
    relative_path: str
    lineno: int
    kind: str
    parameter_count: int
    branch_score: int
    transform_score: int
    deprecated: bool
    replacement: str | None


def _module_name_from_rel(rel: str) -> str:
    path = rel[:-3] if rel.endswith(".py") else rel
    parts = path.split("/")
    if parts and parts[0] == "src":
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(part for part in parts if part)


def _public_top_level_defs(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef]:
    defs: list[ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef] = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if node.name.startswith("_"):
            continue
        defs.append(node)
    return defs


def _decorator_texts(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> list[str]:
    return [_expr_preview(decorator).lower() for decorator in node.decorator_list]


def _docstring_text(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> str:
    return (ast.get_docstring(node) or "").lower()


def _replacement_hint(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> str | None:
    docstring = ast.get_docstring(node) or ""
    for pattern in _REPLACEMENT_PATTERNS:
        match = pattern.search(docstring)
        if match is not None:
            return match.group(1)
    return None


def _node_mentions_deprecated(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> bool:
    text = " ".join([node.name.lower(), _docstring_text(node), *_decorator_texts(node)])
    if any(token in text for token in _DEPRECATED_TOKENS):
        return True
    for child in ast.walk(node):
        if isinstance(child, ast.Call) and _call_tail(child) == "warn":
            preview = _expr_preview(child).lower()
            if "deprecationwarning" in preview or "deprecated" in preview:
                return True
    return False


def _parameter_count(node: ast.AST) -> int:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return 0
    args = node.args
    params = [*args.posonlyargs, *args.args, *args.kwonlyargs]
    return len([param for param in params if param.arg not in {"self", "cls"}])


def _branch_score(node: ast.AST) -> int:
    branch_nodes = (ast.If, ast.IfExp, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.BoolOp, ast.Compare, ast.Match)
    return sum(1 for child in ast.walk(node) if isinstance(child, branch_nodes))


def _transform_score(node: ast.AST) -> int:
    score = 0
    transform_nodes = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp, ast.Subscript)
    for child in ast.walk(node):
        if isinstance(child, transform_nodes):
            score += 1
        if isinstance(child, ast.Call):
            tail = _call_tail(child).lower()
            if tail in {"append", "extend", "update", "get", "split", "join", "strip", "replace", "lower", "upper", "sort", "sorted"}:
                score += 1
    return score


def _production_symbols(parsed_src: list[ParsedFile]) -> list[_ProductionSymbol]:
    symbols: list[_ProductionSymbol] = []
    for pf in parsed_src:
        module = _module_name_from_rel(pf.rel)
        if not module:
            continue
        for node in _public_top_level_defs(pf.tree):
            qualname = f"{module}.{node.name}"
            symbols.append(
                _ProductionSymbol(
                    name=node.name,
                    qualname=qualname,
                    module=module,
                    relative_path=pf.rel,
                    lineno=node.lineno,
                    kind="class" if isinstance(node, ast.ClassDef) else "function",
                    parameter_count=_parameter_count(node),
                    branch_score=_branch_score(node),
                    transform_score=_transform_score(node),
                    deprecated=_node_mentions_deprecated(node),
                    replacement=_replacement_hint(node),
                )
            )
    return symbols


def _module_names(parsed_src: list[ParsedFile]) -> set[str]:
    return {name for pf in parsed_src for name in [_module_name_from_rel(pf.rel)] if name}


def _package_roots(modules: set[str]) -> set[str]:
    return {module.split(".", maxsplit=1)[0] for module in modules if module}


def _reference_tokens_for_tree(tree: ast.AST) -> set[str]:
    tokens: set[str] = set()
    for child in ast.walk(tree):
        if isinstance(child, ast.Name):
            tokens.add(child.id.lower())
        elif isinstance(child, ast.Attribute):
            tokens.add(child.attr.lower())
            dotted = _dotted_name(child).lower()
            if dotted:
                tokens.add(dotted)
        elif isinstance(child, ast.ImportFrom):
            if child.module:
                tokens.add(child.module.lower())
            for alias in child.names:
                tokens.add(alias.name.lower())
                if child.module:
                    tokens.add(f"{child.module}.{alias.name}".lower())
        elif isinstance(child, ast.Import):
            for alias in child.names:
                tokens.add(alias.name.lower())
    return tokens


def _test_reference_tokens(parsed_tests: list[ParsedFile]) -> set[str]:
    tokens: set[str] = set()
    for pf in parsed_tests:
        tokens.update(_reference_tokens_for_tree(pf.tree))
    return tokens


def _integration_test_reference_tokens(parsed_tests: list[ParsedFile]) -> set[str]:
    tokens: set[str] = set()
    for pf in parsed_tests:
        path_claims = any(token in pf.rel.lower() for token in _INTEGRATION_NAME_TOKENS)
        for test_node in _iter_tests(pf.tree):
            name_claims = any(token in test_node.name.lower() for token in _INTEGRATION_NAME_TOKENS)
            if path_claims or name_claims:
                tokens.update(_reference_tokens_for_tree(test_node))
    return tokens


def _symbol_is_referenced(symbol: _ProductionSymbol, tokens: set[str]) -> bool:
    return symbol.name.lower() in tokens or symbol.qualname.lower() in tokens


def _metadata_int(violation: Violation, key: str) -> int:
    value = violation.metadata.get(key)
    return value if isinstance(value, int) else 0


def _coverage_rel_path(path_text: str) -> str | None:
    if not path_text:
        return None
    root = get_config().project_root
    path = Path(path_text)
    if not path.is_absolute():
        path = root / path
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        normalized = path_text.replace("\\", "/")
        marker_index = normalized.find("src/")
        if marker_index >= 0:
            return normalized[marker_index:]
        return normalized


def _coverage_percent_from_json_file(path: Path) -> dict[str, int]:
    try:
        data_obj: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data_obj, dict):
        return {}
    data = cast(dict[str, object], data_obj)
    files_obj = data.get("files")
    if not isinstance(files_obj, dict):
        return {}
    files = cast(dict[str, object], files_obj)
    coverage: dict[str, int] = {}
    for raw_path, raw_entry_obj in files.items():
        if not isinstance(raw_entry_obj, dict):
            continue
        raw_entry = cast(dict[str, object], raw_entry_obj)
        summary_obj = raw_entry.get("summary")
        if not isinstance(summary_obj, dict):
            continue
        summary = cast(dict[str, object], summary_obj)
        percent_obj = summary.get("percent_covered")
        percent: int | float | None = percent_obj if isinstance(percent_obj, (int, float)) else None
        if percent is None:
            display_obj = summary.get("percent_covered_display")
            if isinstance(display_obj, str):
                try:
                    percent = float(display_obj.rstrip("%"))
                except ValueError:
                    percent = None
        if percent is None:
            continue
        rel = _coverage_rel_path(raw_path)
        if rel is not None:
            coverage[rel] = int(round(percent))
    return coverage


def _coverage_percent_from_xml_file(path: Path) -> dict[str, int]:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return {}
    coverage: dict[str, int] = {}
    for class_node in root.findall(".//class"):
        filename = class_node.attrib.get("filename", "")
        rel = _coverage_rel_path(filename)
        if rel is None:
            continue
        line_rate = class_node.attrib.get("line-rate")
        try:
            coverage[rel] = int(round(float(line_rate or "0") * 100))
        except ValueError:
            continue
    return coverage


def _runtime_coverage_by_rel() -> tuple[str, dict[str, int]]:
    """Return existing runtime coverage report data if pytest-cov already wrote it.

    The linter intentionally does not run tests; it only consumes coverage.json or
    coverage.xml artifacts that are already present in the project root.
    """
    root = get_config().project_root
    for name in _COVERAGE_JSON_NAMES:
        coverage = _coverage_percent_from_json_file(root / name)
        if coverage:
            return name, coverage
    for name in _COVERAGE_XML_NAMES:
        coverage = _coverage_percent_from_xml_file(root / name)
        if coverage:
            return name, coverage
    return "static-reference", {}


def detect_untested_production_code(
    src_files: list[Path] | list[ParsedFile] | None = None,
    test_files: list[Path] | list[ParsedFile] | None = None,
) -> list[Violation]:
    """Find production modules with low runtime or static test coverage.

    If a coverage.json/coverage.xml report exists, findings are sorted by real
    runtime line coverage. Otherwise the detector falls back to static reference
    coverage by public symbol name and says so in the output.
    """
    parsed_src = ensure_parsed(src_files, fallback=[])
    parsed_tests = ensure_parsed(test_files, fallback=find_test_files())
    refs = _test_reference_tokens(parsed_tests)
    coverage_source, runtime_coverage = _runtime_coverage_by_rel()
    by_path: dict[str, list[_ProductionSymbol]] = {}
    for symbol in _production_symbols(parsed_src):
        by_path.setdefault(symbol.relative_path, []).append(symbol)

    violations: list[Violation] = []
    for rel, symbols in by_path.items():
        if not symbols:
            continue
        referenced = [symbol for symbol in symbols if _symbol_is_referenced(symbol, refs)]
        missing = [symbol.name for symbol in symbols if symbol not in referenced]
        static_coverage = int(round(100 * len(referenced) / len(symbols)))
        if runtime_coverage:
            coverage = runtime_coverage.get(rel, 0)
            if coverage >= 80:
                continue
            detail = (
                f"runtime_line_coverage={coverage}% from {coverage_source}; "
                f"static_test_reference_coverage={static_coverage}% "
                f"({len(referenced)}/{len(symbols)} public symbols referenced); "
                f"unreferenced={', '.join(missing[:8]) or 'none'}"
            )
            metadata = dict[str, object]()
            metadata["coverage_kind"] = "runtime-line"
            metadata["coverage_source"] = coverage_source
            metadata["coverage_percent"] = coverage
            metadata["static_reference_coverage_percent"] = static_coverage
            metadata["unreferenced_symbols"] = missing[:20]
        else:
            coverage = static_coverage
            if coverage >= 50:
                continue
            detail = (
                f"static_test_reference_coverage={coverage}% "
                f"({len(referenced)}/{len(symbols)} public symbols referenced); "
                f"unreferenced={', '.join(missing[:8])}; no coverage.json/coverage.xml found"
            )
            metadata = dict[str, object]()
            metadata["coverage_kind"] = "static-reference"
            metadata["coverage_percent"] = coverage
            metadata["unreferenced_symbols"] = missing[:20]
        violations.append(
            Violation(
                rule="untested-production-code",
                relative_path=rel,
                identifier=f"coverage-{coverage:03d}",
                detail=detail,
                metadata=metadata,
            )
        )
    return sorted(violations, key=lambda v: (_metadata_int(v, "coverage_percent"), v.relative_path))


def _production_call_sites(parsed_src: list[ParsedFile]) -> dict[str, list[str]]:
    symbols = _production_symbols(parsed_src)
    name_counts = Counter(symbol.name for symbol in symbols)
    unique_function_names = {
        symbol.name
        for symbol in symbols
        if symbol.kind == "function" and name_counts[symbol.name] == 1
    }
    sites: dict[str, set[str]] = {name: set() for name in unique_function_names}
    for pf in parsed_src:
        for child in ast.walk(pf.tree):
            if not isinstance(child, ast.Call):
                continue
            tail = _call_tail(child)
            if tail not in unique_function_names:
                continue
            sites.setdefault(tail, set()).add(f"{pf.rel}:{child.lineno}")
    return {name: sorted(values) for name, values in sites.items() if values}


def _has_token(text: str, tokens: set[str]) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in tokens)


def _is_utility_or_trivial_helper(symbol: _ProductionSymbol) -> bool:
    lowered_name = symbol.name.lower()
    lowered_module = f".{symbol.module.lower()}"
    if lowered_name.startswith(_INTEGRATION_HELPER_NAME_PREFIXES):
        return True
    if lowered_name in _INTEGRATION_UTILITY_NAME_TOKENS:
        return True
    if any(token in lowered_module for token in _INTEGRATION_UTILITY_MODULE_TOKENS):
        return True
    if (
        symbol.branch_score <= 1
        and symbol.transform_score <= 1
        and symbol.parameter_count <= 2
        and not _has_token(f"{symbol.module}.{symbol.name}", _INTEGRATION_SEAM_TOKENS)
    ):
        return True
    return False


def _integration_seam_score(symbol: _ProductionSymbol, callers: int) -> tuple[int, list[str]]:
    score = callers
    reasons = [f"callers={callers}"]
    text = f"{symbol.module}.{symbol.name}".lower()
    seam_hits = [token for token in sorted(_INTEGRATION_SEAM_TOKENS) if token in text]
    if seam_hits:
        score += 6
        reasons.append(f"seam-role={', '.join(seam_hits[:3])}")
    if symbol.branch_score >= 3:
        score += min(symbol.branch_score, 4)
        reasons.append(f"branches={symbol.branch_score}")
    if symbol.transform_score >= 2:
        score += min(symbol.transform_score, 4)
        reasons.append(f"transforms={symbol.transform_score}")
    if callers >= 5:
        score += 2
        reasons.append("high fan-in")
    if _is_utility_or_trivial_helper(symbol):
        score -= 8
        reasons.append("utility/trivial-helper discount")
    return score, reasons


def detect_missing_integration_tests(
    src_files: list[Path] | list[ParsedFile] | None = None,
    test_files: list[Path] | list[ParsedFile] | None = None,
) -> list[Violation]:
    """Find reused production seams that lack integration/e2e references.

    The detector intentionally discounts tiny utilities/formatting helpers so the
    queue prioritizes dataflow, orchestration, parser, store, handler, API, and
    UI seams instead of high-fan-in leaf helpers such as markup/style functions.
    """
    parsed_src = ensure_parsed(src_files, fallback=[])
    parsed_tests = ensure_parsed(test_files, fallback=find_test_files())
    integration_refs = _integration_test_reference_tokens(parsed_tests)
    call_sites = _production_call_sites(parsed_src)
    violations: list[Violation] = []
    for symbol in _production_symbols(parsed_src):
        callers = len(call_sites.get(symbol.name, []))
        if (
            symbol.kind != "function"
            or callers < 2
            or not _has_token(f"{symbol.module}.{symbol.name}", _INTEGRATION_SEAM_TOKENS)
            or _is_utility_or_trivial_helper(symbol)
            or _symbol_is_referenced(symbol, integration_refs)
        ):
            continue
        seam_score, reasons = _integration_seam_score(symbol, callers)
        if seam_score < 8:
            continue
        violations.append(
            Violation(
                rule="missing-integration-test",
                relative_path=symbol.relative_path,
                identifier=symbol.qualname,
                detail=(
                    f"line {symbol.lineno}: production_callers={callers}; "
                    f"seam_score={seam_score}; reasons={'; '.join(reasons)}; "
                    f"no integration/e2e/pipeline test references `{symbol.name}`"
                ),
                metadata={
                    "caller_count": callers,
                    "seam_score": seam_score,
                    "symbol": symbol.qualname,
                    "caller_sites": call_sites.get(symbol.name, [])[:10],
                    "reasons": reasons,
                },
            )
        )
    return sorted(
        violations,
        key=lambda v: (-_metadata_int(v, "caller_count"), -_metadata_int(v, "seam_score"), v.relative_path, v.identifier),
    )


def _hypothesis_properties(symbol: _ProductionSymbol) -> list[str]:
    text = f"{symbol.module}.{symbol.name}".lower()
    properties: list[str] = []
    if any(token in text for token in ("parse", "serialize", "deserialize", "encode", "decode")):
        properties.append("round-trip / malformed-input contracts")
    if any(token in text for token in ("normalize", "canonical", "clean", "coerce")):
        properties.append("idempotence / canonicalization")
    if any(token in text for token in ("sort", "rank", "score", "order")):
        properties.append("ordering / monotonicity")
    if any(token in text for token in ("dedupe", "unique", "merge", "filter")):
        properties.append("dedup/filter/merge invariants")
    if any(token in text for token in ("bound", "limit", "clamp", "range", "validate")):
        properties.append("bounds / invalid-input rejection")
    if not properties and symbol.transform_score >= 3:
        properties.append("collection/string transform invariants")
    if not properties and symbol.branch_score >= 4:
        properties.append("branch decision-table invariants")
    return properties


def _hypothesis_score(symbol: _ProductionSymbol) -> tuple[int, list[str], list[str]]:
    score = 0
    reasons: list[str] = []
    lowered = symbol.name.lower()
    name_hits = [token for token in _HYPOTHESIS_NAME_TOKENS if token in lowered]
    if name_hits:
        score += 2
        reasons.append(f"name suggests invariant work ({', '.join(name_hits[:3])})")
    if symbol.parameter_count >= 2:
        score += 2
        reasons.append(f"{symbol.parameter_count} inputs")
    elif symbol.parameter_count == 1:
        score += 1
        reasons.append("input domain")
    if symbol.branch_score >= 4:
        score += 2
        reasons.append(f"branch/validation paths={symbol.branch_score}")
    elif symbol.branch_score >= 2:
        score += 1
        reasons.append(f"branches={symbol.branch_score}")
    if symbol.transform_score >= 3:
        score += 2
        reasons.append(f"collection/string transforms={symbol.transform_score}")
    elif symbol.transform_score:
        score += 1
        reasons.append("data transformation")
    properties = _hypothesis_properties(symbol)
    if properties:
        reasons.append(f"candidate properties={'; '.join(properties[:2])}")
    return score, reasons, properties


def detect_hypothesis_candidates(
    src_files: list[Path] | list[ParsedFile] | None = None,
    test_files: list[Path] | list[ParsedFile] | None = None,
) -> list[Violation]:
    """Find tested production functions likely to benefit from property-based tests."""
    parsed_src = ensure_parsed(src_files, fallback=[])
    parsed_tests = ensure_parsed(test_files, fallback=find_test_files())
    refs = _test_reference_tokens(parsed_tests)
    hypothesis_refs: set[str] = set()
    for pf in parsed_tests:
        source = "\n".join(pf.lines).lower()
        if "hypothesis" not in source and "@given" not in source and "given(" not in source:
            continue
        hypothesis_refs.update(_reference_tokens_for_tree(pf.tree))

    violations: list[Violation] = []
    for symbol in _production_symbols(parsed_src):
        if symbol.kind != "function" or not _symbol_is_referenced(symbol, refs):
            continue
        if _symbol_is_referenced(symbol, hypothesis_refs):
            continue
        score, reasons, properties = _hypothesis_score(symbol)
        if score < 4:
            continue
        violations.append(
            Violation(
                rule="hypothesis-candidate",
                relative_path=symbol.relative_path,
                identifier=symbol.qualname,
                detail=(
                    f"line {symbol.lineno}: property_test_score={score}; "
                    f"reasons={'; '.join(reasons)}; no Hypothesis/given test reference"
                ),
                metadata={"property_test_score": score, "reasons": reasons, "candidate_properties": properties},
            )
        )
    return sorted(violations, key=lambda v: (-_metadata_int(v, "property_test_score"), v.relative_path, v.identifier))


def _missing_production_imports(parsed_tests: list[ParsedFile], modules: set[str]) -> list[Violation]:
    roots = _package_roots(modules)
    violations: list[Violation] = []
    for pf in parsed_tests:
        for child in ast.walk(pf.tree):
            if isinstance(child, ast.ImportFrom) and child.module:
                module = child.module
                root = module.split(".", maxsplit=1)[0]
                if root in roots and module not in modules:
                    imported_names = [alias.name for alias in child.names]
                    violations.append(
                        Violation(
                            rule="obsolete-or-deprecated-test",
                            relative_path=pf.rel,
                            identifier=f"line-{child.lineno}",
                            detail=(
                                f"imports missing production module `{module}`; "
                                f"imported={', '.join(imported_names[:6])}"
                            ),
                            metadata={"module": module, "line": child.lineno, "imported_names": imported_names},
                        )
                    )
            elif isinstance(child, ast.Import):
                for alias in child.names:
                    module = alias.name
                    root = module.split(".", maxsplit=1)[0]
                    if root in roots and module not in modules and not any(
                        existing.startswith(f"{module}.") for existing in modules
                    ):
                        violations.append(
                            Violation(
                                rule="obsolete-or-deprecated-test",
                                relative_path=pf.rel,
                                identifier=f"line-{child.lineno}",
                                detail=f"imports missing production module `{module}`",
                                metadata={"module": module, "line": child.lineno, "imported_names": [module]},
                            )
                        )
    return violations


def detect_obsolete_or_deprecated_tests(
    src_files: list[Path] | list[ParsedFile] | None = None,
    test_files: list[Path] | list[ParsedFile] | None = None,
) -> list[Violation]:
    """Find tests tied to missing modules or deprecated/obsolete production APIs."""
    parsed_src = ensure_parsed(src_files, fallback=[])
    parsed_tests = ensure_parsed(test_files, fallback=find_test_files())
    modules = _module_names(parsed_src)
    violations = _missing_production_imports(parsed_tests, modules)
    deprecated_symbols = [symbol for symbol in _production_symbols(parsed_src) if symbol.deprecated]
    if not deprecated_symbols:
        return sorted(violations, key=lambda v: (v.relative_path, v.identifier))

    for pf in parsed_tests:
        refs = _reference_tokens_for_tree(pf.tree)
        for symbol in deprecated_symbols:
            if not _symbol_is_referenced(symbol, refs):
                continue
            replacement = f"; replacement={symbol.replacement}" if symbol.replacement else ""
            metadata: ObjectDict = {"symbol": symbol.qualname, "production_path": symbol.relative_path}
            if symbol.replacement:
                metadata["replacement"] = symbol.replacement
            violations.append(
                Violation(
                    rule="obsolete-or-deprecated-test",
                    relative_path=pf.rel,
                    identifier=symbol.qualname,
                    detail=f"test references deprecated production {symbol.kind} `{symbol.qualname}`{replacement}",
                    metadata=metadata,
                )
            )
    return sorted(violations, key=lambda v: (v.relative_path, v.identifier))
