"""Audit tests for staging hook rules.

These tests validate false-positive resistance, false-negative coverage,
and stability of the new hook rules before they're wired into production.

Run: python -m pytest _staging/test_audit.py -v
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass, field
from typing import cast

import pytest

from slopgate.context import HookContext
from slopgate.models import RuleFinding
from slopgate.rules.base import Rule

from .test_audit_cases import (
    ALL_STAGING_RULES,
    DUPLICATE_RULE_CASES,
    STABILITY_SOURCES,
    TEST_SMELL_RULE_CASES,
)


# ---------------------------------------------------------------------------
# Minimal stub context for unit-testing rules in isolation
# ---------------------------------------------------------------------------


@dataclass
class _FakeConfig:
    python_ast_enabled: bool = True
    python_ast_max_parse_chars: int = 500_000
    enabled_rules: dict[str, bool] = field(default_factory=dict)


@dataclass
class _FakeContentTarget:
    path: str
    content: str


@dataclass
class _FakeContext:
    event_name: str = "PreToolUse"
    tool_name: str = "Edit"
    config: _FakeConfig = field(default_factory=_FakeConfig)
    candidate_paths: list[str] = field(default_factory=list)
    content_targets: list[_FakeContentTarget] = field(default_factory=list)
    cwd: str = "/tmp"


RuleType = type[Rule]


def _evaluate_rule(rule: Rule, ctx: _FakeContext) -> list[RuleFinding]:
    return rule.evaluate(cast(HookContext, ctx))


def _evaluate_source(
    rule_type: RuleType,
    source: str,
    *,
    path: str = "src/example.py",
) -> list[RuleFinding]:
    return _evaluate_rule(
        rule_type(),
        _FakeContext(
            content_targets=[_FakeContentTarget(path, textwrap.dedent(source))]
        ),
    )


def _assert_finding_state(
    rule_type: RuleType,
    source: str,
    *,
    should_find: bool,
    path: str = "src/example.py",
) -> None:
    findings = _evaluate_source(rule_type, source, path=path)
    if should_find:
        assert findings, "expected at least one finding"
    else:
        assert not findings, "expected no findings"


# ---------------------------------------------------------------------------
# PY-DUP-001 through PY-DUP-004: duplicate-code rules
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("_case", "rule_type", "should_find", "raw_source"),
    DUPLICATE_RULE_CASES,
    ids=[case[0] for case in DUPLICATE_RULE_CASES],
)
def test_duplicate_rule_cases(
    _case: str,
    rule_type: RuleType,
    should_find: bool,
    raw_source: str,
) -> None:
    _assert_finding_state(rule_type, raw_source, should_find=should_find)


# ---------------------------------------------------------------------------
# PY-TEST-001 through PY-TEST-004: test-smell rules
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "case", TEST_SMELL_RULE_CASES, ids=[case[0] for case in TEST_SMELL_RULE_CASES]
)
def test_test_smell_rule_cases(case: tuple[str, RuleType, bool, str, str]) -> None:
    _case, rule_type, should_find, path, raw_source = case
    _assert_finding_state(
        rule_type,
        raw_source,
        should_find=should_find,
        path=path,
    )


# ---------------------------------------------------------------------------
# Stability: ensure rules don't crash on edge-case inputs
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("_case", "source"),
    STABILITY_SOURCES,
    ids=[case[0] for case in STABILITY_SOURCES],
)
def test_stability_edge_cases(_case: str, source: str) -> None:
    for rule_type in ALL_STAGING_RULES:
        findings = _evaluate_source(rule_type, source)
        assert isinstance(findings, list), f"{rule_type.rule_id} returned non-list"
