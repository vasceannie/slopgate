"""PY-TEST-001 through PY-TEST-004: Test-smell hook rules.

Port the lint-only test smell detectors into reactive hooks so that
eager tests, assertion roulette, fixtures outside conftest, and
conditional assertions are caught at write time.

Staging: not yet registered in the rule registry.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING, final
from typing_extensions import override

from slopgate.constants import (
    METADATA_FUNCTION,
    METADATA_PATH,
    PERMISSION_REQUEST,
    POST_TOOL_USE,
    PRE_TOOL_USE,
)
from slopgate.lint._detectors.test_smells import (
    count_sut_calls,
    is_pytest_fixture_decorator,
    max_bare_assert_run,
)
from slopgate.models import RuleFinding, Severity
from slopgate.rules.base import Rule, is_rule_enabled

from .._helpers import decision_for_context, evaluate_common
from ._test_smell_rule_helpers import (
    contains_assertion,
    is_test_function,
    is_type_checking_block,
    iter_test_module_nodes,
    walk_skip_nested_funcs,
)

if TYPE_CHECKING:
    from slopgate.context import HookContext

_TEST_RULE_EVENTS = (PRE_TOOL_USE, PERMISSION_REQUEST, POST_TOOL_USE)

# ---------------------------------------------------------------------------
# PY-TEST-001: Eager tests (too many SUT calls)
# ---------------------------------------------------------------------------


@final
class PythonEagerTestRule(Rule):
    """Detect test functions with too many calls to the system under test.

    Eager tests try to verify too many behaviours in one function,
    making them fragile and hard to understand.
    """

    rule_id = "PY-TEST-001"
    title = "Block eager tests"
    events = _TEST_RULE_EVENTS

    _MAX_SUT_CALLS = 5  # threshold

    def _check_source(
        self, source: str, path_value: str, ctx: HookContext
    ) -> list[RuleFinding]:
        findings: list[RuleFinding] = []
        for node in iter_test_module_nodes(source, path_value, ctx):
            if not is_test_function(node):
                continue
            calls = count_sut_calls(node)
            if calls > self._MAX_SUT_CALLS:
                findings.append(
                    RuleFinding(
                        rule_id=self.rule_id,
                        title=self.title,
                        severity=Severity.MEDIUM,
                        decision=decision_for_context(ctx),
                        message=(
                            f"Test `{node.name}` in `{path_value}` makes {calls} "
                            f"SUT calls (max: {self._MAX_SUT_CALLS}). "
                            f"Split into focused single-behaviour tests."
                        ),
                        metadata={
                            METADATA_PATH: path_value,
                            METADATA_FUNCTION: node.name,
                            "sut_calls": calls,
                        },
                    )
                )
        return findings

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        return evaluate_common(self, ctx, self._check_source)


# ---------------------------------------------------------------------------
# PY-TEST-002: Assertion roulette (bare asserts without messages)
# ---------------------------------------------------------------------------


@final
class PythonAssertionRouletteRule(Rule):
    """Detect test functions with long runs of bare ``assert`` (no message).

    When multiple bare asserts fail, it's unclear which one broke.
    Each assert should have a descriptive message or use named matchers.
    """

    rule_id = "PY-TEST-002"
    title = "Block assertion roulette"
    events = _TEST_RULE_EVENTS

    _MAX_CONSECUTIVE = 3  # flag if more than this many bare asserts in a row

    def _check_source(
        self, source: str, path_value: str, ctx: HookContext
    ) -> list[RuleFinding]:
        findings: list[RuleFinding] = []
        for node in iter_test_module_nodes(source, path_value, ctx):
            if not is_test_function(node):
                continue
            max_run = max_bare_assert_run(node.body)
            if max_run > self._MAX_CONSECUTIVE:
                findings.append(
                    RuleFinding(
                        rule_id=self.rule_id,
                        title=self.title,
                        severity=Severity.MEDIUM,
                        decision=decision_for_context(ctx),
                        message=(
                            f"Test `{node.name}` in `{path_value}` has {max_run} "
                            f"consecutive bare asserts (max: {self._MAX_CONSECUTIVE}). "
                            f"Add descriptive messages or use named matchers."
                        ),
                        metadata={
                            METADATA_PATH: path_value,
                            METADATA_FUNCTION: node.name,
                            "consecutive_bare_asserts": max_run,
                        },
                    )
                )
        return findings

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        return evaluate_common(self, ctx, self._check_source)


# ---------------------------------------------------------------------------
# PY-TEST-003: Fixtures outside conftest.py
# ---------------------------------------------------------------------------


@final
class PythonFixtureOutsideConftestRule(Rule):
    """Detect @pytest.fixture definitions in files other than conftest.py.

    Fixtures scattered across test files are hard to discover and reuse.
    Centralise them in conftest.py files.
    """

    rule_id = "PY-TEST-003"
    title = "Block fixtures outside conftest"
    events = _TEST_RULE_EVENTS

    def _check_source(
        self, source: str, path_value: str, ctx: HookContext
    ) -> list[RuleFinding]:
        # Skip conftest.py itself (exact basename match)
        if Path(path_value).name == "conftest.py":
            return []
        findings: list[RuleFinding] = []
        for node in iter_test_module_nodes(source, path_value, ctx):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                if is_pytest_fixture_decorator(dec):
                    findings.append(
                        RuleFinding(
                            rule_id=self.rule_id,
                            title=self.title,
                            severity=Severity.MEDIUM,
                            decision=decision_for_context(ctx),
                            message=(
                                f"Fixture `{node.name}` defined outside conftest.py "
                                f"in `{path_value}` (line {node.lineno}). "
                                f"Move to the nearest conftest.py for discoverability."
                            ),
                            metadata={
                                METADATA_PATH: path_value,
                                METADATA_FUNCTION: node.name,
                                "line": node.lineno,
                            },
                        )
                    )
                    break  # one finding per function
        return findings

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        return evaluate_common(self, ctx, self._check_source)


# ---------------------------------------------------------------------------
# PY-TEST-004: Conditional assertions (asserts inside if/for/while)
# ---------------------------------------------------------------------------


@final
class PythonConditionalAssertionRule(Rule):
    """Detect assertions inside if/for/while blocks in test functions.

    Conditional assertions make tests non-deterministic: the same test
    run may execute different assertions depending on runtime state.
    """

    rule_id = "PY-TEST-004"
    title = "Block conditional assertions"
    events = _TEST_RULE_EVENTS

    def _check_source(
        self, source: str, path_value: str, ctx: HookContext
    ) -> list[RuleFinding]:
        findings: list[RuleFinding] = []
        for node in iter_test_module_nodes(source, path_value, ctx):
            if not is_test_function(node):
                continue
            for child in walk_skip_nested_funcs(node):
                if isinstance(child, (ast.For, ast.While, ast.If, ast.AsyncFor)):
                    if is_type_checking_block(child):
                        continue
                    if contains_assertion(child):
                        findings.append(
                            RuleFinding(
                                rule_id=self.rule_id,
                                title=self.title,
                                severity=Severity.MEDIUM,
                                decision=decision_for_context(ctx),
                                message=(
                                    f"Test `{node.name}` in `{path_value}` has "
                                    f"assertions inside a {type(child).__name__} "
                                    f"at line {child.lineno}. "
                                    f"Extract into a separate focused test."
                                ),
                                metadata={
                                    METADATA_PATH: path_value,
                                    METADATA_FUNCTION: node.name,
                                    "control_flow": type(child).__name__,
                                    "line": child.lineno,
                                },
                            )
                        )
                        break  # one finding per test function
        return findings

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        return evaluate_common(self, ctx, self._check_source)
