from __future__ import annotations

from pathlib import Path

from tests.integration.test_python_ast_rule_public_api import context_with_limits
from slopgate.rules.python_ast._staging import test_audit
from slopgate.rules.python_ast._staging.duplicate_rules import (
    PythonDuplicateCallSequenceRule,
    PythonRepeatedBlocksRule,
    PythonRepeatedMagicNumberRule,
    PythonSemanticCloneRule,
)
from slopgate.rules.python_ast._staging.test_smell_rules import (
    PythonAssertionRouletteRule,
    PythonConditionalAssertionRule,
    PythonEagerTestRule,
    PythonFixtureOutsideConftestRule,
)


def test_repeated_blocks_rule_reports_first_repeated_scope(tmp_path: Path) -> None:
    source = """
def one():
    a = 1
    b = 2
    c = 3
    return a + b + c

def two():
    a = 1
    b = 2
    c = 3
    return a + b + c
""".lstrip()
    ctx = context_with_limits(tmp_path, source)

    findings = PythonRepeatedBlocksRule().evaluate(ctx)

    assert [(item.rule_id, item.metadata.get("scope")) for item in findings[:1]] == [
        ("PY-DUP-001", "one")
    ]


def test_duplicate_call_sequence_rule_reports_shared_sequence(tmp_path: Path) -> None:
    source = """
def one():
    load()
    transform()
    save()

def two():
    load()
    transform()
    save()
""".lstrip()
    ctx = context_with_limits(tmp_path, source)

    findings = PythonDuplicateCallSequenceRule().evaluate(ctx)

    assert [(item.rule_id, item.metadata.get("duplicates")) for item in findings] == [
        ("PY-DUP-002", ["one", "two"])
    ]


def test_repeated_magic_number_rule_reports_worst_numeric_literal(tmp_path: Path) -> None:
    ctx = context_with_limits(tmp_path, "def one():\n    return 42 + 42 + 42 + 42\n")

    findings = PythonRepeatedMagicNumberRule().evaluate(ctx)

    assert [(item.rule_id, item.metadata.get("value")) for item in findings] == [
        ("PY-DUP-004", 42)
    ]


def test_semantic_clone_rule_reports_structural_clone_pair(tmp_path: Path) -> None:
    source = """
def one(value):
    total = value + 1
    result = total * 3
    return result

def two(item):
    total = item + 1
    result = total * 3
    return result
""".lstrip()
    ctx = context_with_limits(tmp_path, source)

    findings = PythonSemanticCloneRule().evaluate(ctx)

    assert [(item.rule_id, item.metadata.get("clones")) for item in findings] == [
        ("PY-DUP-003", ["one", "two"])
    ]


def test_eager_test_rule_reports_excess_sut_calls(tmp_path: Path) -> None:
    source = """
def test_many_calls():
    run()
    run()
    run()
    run()
    run()
    run()
""".lstrip()
    ctx = context_with_limits(tmp_path, source, path="tests/test_sample.py")

    findings = PythonEagerTestRule().evaluate(ctx)

    assert [(item.rule_id, item.metadata.get("sut_calls")) for item in findings] == [
        ("PY-TEST-001", 6)
    ]


def test_assertion_roulette_rule_reports_bare_assert_run(tmp_path: Path) -> None:
    source = """
def test_many_asserts():
    assert alpha
    assert beta
    assert gamma
    assert delta
""".lstrip()
    ctx = context_with_limits(tmp_path, source, path="tests/test_sample.py")

    findings = PythonAssertionRouletteRule().evaluate(ctx)

    assert [
        (item.rule_id, item.metadata.get("consecutive_bare_asserts"))
        for item in findings
    ] == [("PY-TEST-002", 4)]


def test_fixture_outside_conftest_rule_reports_fixture_function(tmp_path: Path) -> None:
    source = """
import pytest

@pytest.fixture
def item():
    return 1
""".lstrip()
    ctx = context_with_limits(tmp_path, source, path="tests/test_sample.py")

    findings = PythonFixtureOutsideConftestRule().evaluate(ctx)

    assert [(item.rule_id, item.metadata.get("function")) for item in findings] == [
        ("PY-TEST-003", "item")
    ]


def test_conditional_assertion_rule_reports_control_flow(tmp_path: Path) -> None:
    source = """
def test_branch(flag):
    if flag:
        assert flag
""".lstrip()
    ctx = context_with_limits(tmp_path, source, path="tests/test_sample.py")

    findings = PythonConditionalAssertionRule().evaluate(ctx)

    assert [(item.rule_id, item.metadata.get("control_flow")) for item in findings] == [
        ("PY-TEST-004", "If")
    ]


def test_staging_audit_cases_remain_callable() -> None:
    assert {
        "duplicate": callable(test_audit.test_duplicate_rule_cases),
        "test_smell": callable(test_audit.test_test_smell_rule_cases),
        "stability": callable(test_audit.test_stability_edge_cases),
    } == {
        "duplicate": True,
        "test_smell": True,
        "stability": True,
    }
