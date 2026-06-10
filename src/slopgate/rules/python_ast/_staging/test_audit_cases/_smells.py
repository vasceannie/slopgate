"""Test-smell rule cases."""

from __future__ import annotations

from slopgate.rules.base import Rule
from slopgate.rules.python_ast._staging.test_smell_rules import (
    PythonAssertionRouletteRule,
    PythonConditionalAssertionRule,
    PythonEagerTestRule,
    PythonFixtureOutsideConftestRule,
)

RuleType = type[Rule]

TEST_SMELL_RULE_CASES: tuple[tuple[str, RuleType, bool, str, str], ...] = (
    (
        "eager_detects_many_sut_calls",
        PythonEagerTestRule,
        True,
        "tests/test_example.py",
        """\
        def test_everything():
            result1 = calculate(1)
            result2 = calculate(2)
            result3 = calculate(3)
            result4 = calculate(4)
            result5 = calculate(5)
            result6 = calculate(6)
        """,
    ),
    (
        "eager_reasonable_test",
        PythonEagerTestRule,
        False,
        "tests/test_example.py",
        """\
        def test_foo():
            result = calculate(1)
            assert result == 42
        """,
    ),
    (
        "eager_skips_non_test_file",
        PythonEagerTestRule,
        False,
        "src/production.py",
        """\
        def test_everything():
            calculate(1)
            calculate(2)
            calculate(3)
            calculate(4)
            calculate(5)
            calculate(6)
        """,
    ),
    (
        "eager_ignores_setup_calls",
        PythonEagerTestRule,
        False,
        "tests/test_example.py",
        """\
        def test_with_mocks():
            mock = mock.Mock()
            patch("something")
            fixture("data")
            result = sut.run()
            sut.verify()
        """,
    ),
    (
        "roulette_detects_bare_assert_run",
        PythonAssertionRouletteRule,
        True,
        "tests/test_example.py",
        """\
        def test_stuff():
            assert a == 1
            assert b == 2
            assert c == 3
            assert d == 4
        """,
    ),
    (
        "roulette_ignores_assert_messages",
        PythonAssertionRouletteRule,
        False,
        "tests/test_example.py",
        """\
        def test_stuff():
            assert a == 1, "a should be 1"
            assert b == 2, "b should be 2"
            assert c == 3, "c should be 3"
            assert d == 4, "d should be 4"
        """,
    ),
    (
        "roulette_reasonable_count",
        PythonAssertionRouletteRule,
        False,
        "tests/test_example.py",
        """\
        def test_stuff():
            assert a == 1
            assert b == 2
            assert c == 3
        """,
    ),
    (
        "fixture_detects_test_file_fixture",
        PythonFixtureOutsideConftestRule,
        True,
        "tests/test_example.py",
        """\
        import pytest

        @pytest.fixture
        def sample_data():
            return [1, 2, 3]
        """,
    ),
    (
        "fixture_allows_conftest",
        PythonFixtureOutsideConftestRule,
        False,
        "tests/conftest.py",
        """\
        import pytest

        @pytest.fixture
        def sample_data():
            return [1, 2, 3]
        """,
    ),
    (
        "fixture_allows_regular_function",
        PythonFixtureOutsideConftestRule,
        False,
        "tests/test_example.py",
        """\
        def helper():
            return [1, 2, 3]
        """,
    ),
    (
        "fixture_detects_direct_fixture_import",
        PythonFixtureOutsideConftestRule,
        True,
        "tests/test_example.py",
        """\
        from pytest import fixture

        @fixture
        def sample_data():
            return [1, 2, 3]
        """,
    ),
    (
        "conditional_detects_assertion_in_if",
        PythonConditionalAssertionRule,
        True,
        "tests/test_example.py",
        """\
        def test_conditional():
            if condition:
                assert result == expected
        """,
    ),
    (
        "conditional_detects_assertion_in_for",
        PythonConditionalAssertionRule,
        True,
        "tests/test_example.py",
        """\
        def test_loop():
            for item in items:
                assert item.valid
        """,
    ),
    (
        "conditional_allows_top_level_assert",
        PythonConditionalAssertionRule,
        False,
        "tests/test_example.py",
        """\
        def test_simple():
            result = calculate()
            assert result == 42
        """,
    ),
    (
        "conditional_skips_non_test_file",
        PythonConditionalAssertionRule,
        False,
        "src/production.py",
        """\
        def process():
            if error:
                assert False, "should not happen"
        """,
    ),
)
