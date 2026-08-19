"""Collectors that scan project test files."""

from __future__ import annotations

from slopgate.lint._collector_groups.scheduling import CollectorSpec, execute_all
from slopgate.lint._collector_groups.types import CollectorResults
from slopgate.lint._helpers import ParsedFile


def test_collector_specs(parsed_tests: list[ParsedFile]) -> list[CollectorSpec]:
    """Return deferred collectors for project test modules."""
    from slopgate.lint._detectors.test_smells import (
        detect_assertion_free_tests,
        detect_assertion_roulette,
        detect_conditional_assertions,
        detect_eager_tests,
        detect_fixtures_outside_conftest,
        detect_long_tests,
        detect_pytest_asyncio_patterns,
    )

    return [
        CollectorSpec("long-test", lambda: detect_long_tests(parsed_tests)),
        CollectorSpec("eager-test", lambda: detect_eager_tests(parsed_tests)),
        CollectorSpec(
            "assertion-free-test", lambda: detect_assertion_free_tests(parsed_tests)
        ),
        CollectorSpec(
            "assertion-roulette", lambda: detect_assertion_roulette(parsed_tests)
        ),
        CollectorSpec(
            "conditional-assertion",
            lambda: detect_conditional_assertions(parsed_tests),
        ),
        CollectorSpec(
            "fixture-outside-conftest",
            lambda: detect_fixtures_outside_conftest(parsed_tests),
        ),
        CollectorSpec(
            "pytest-asyncio-pattern",
            lambda: detect_pytest_asyncio_patterns(parsed_tests),
        ),
    ]


def test_collectors(parsed_tests: list[ParsedFile]) -> CollectorResults:
    """Collect all test-file violation pairs."""
    return execute_all(test_collector_specs(parsed_tests))
