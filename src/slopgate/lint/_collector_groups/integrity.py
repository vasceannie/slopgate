"""Test-integrity collector groups."""

from __future__ import annotations

from slopgate.lint._collector_groups.types import CollectorResults
from slopgate.lint._helpers import ParsedFile


def touched_integrity_collectors(parsed_tests: list[ParsedFile]) -> CollectorResults:
    """Collect touched-test checks without building a suite-wide index."""
    from slopgate.lint._detectors.test_smells import (
        detect_hand_built_test_payloads,
        detect_mock_theater,
        detect_mocked_integration_tests,
        detect_schema_bypasses,
        detect_weak_assertions,
    )

    return [
        ("weak-test-assertion", detect_weak_assertions(parsed_tests)),
        ("mock-theater", detect_mock_theater(parsed_tests)),
        ("schema-bypass-test-data", detect_schema_bypasses(parsed_tests)),
        ("hand-built-test-payload", detect_hand_built_test_payloads(parsed_tests)),
        ("mocked-integration-test", detect_mocked_integration_tests(parsed_tests)),
    ]


def full_integrity_collectors(
    parsed_src: list[ParsedFile],
    parsed_tests: list[ParsedFile],
    *,
    parsed_test_targets: list[ParsedFile] | None = None,
) -> CollectorResults:
    """Collect bad-test-efficacy and holistic suite-quality indicators."""
    from slopgate.lint._detectors.test_smells import (
        build_test_integrity_index,
        detect_coverage_artifact_incomplete,
        detect_hypothesis_candidates,
        detect_missing_integration_tests,
        detect_possibly_dead_internal,
        detect_stale_test_references,
        detect_untested_public_api,
    )

    index = build_test_integrity_index(parsed_src, parsed_tests)
    test_targets = parsed_tests if parsed_test_targets is None else parsed_test_targets
    return [
        ("untested-public-api", detect_untested_public_api(index=index)),
        (
            "coverage-artifact-incomplete",
            detect_coverage_artifact_incomplete(index=index),
        ),
        ("possibly-dead-internal", detect_possibly_dead_internal(index=index)),
        ("missing-integration-test", detect_missing_integration_tests(index=index)),
        ("hypothesis-candidate", detect_hypothesis_candidates(index=index)),
        ("obsolete-or-deprecated-test", detect_stale_test_references(index=index)),
        *touched_integrity_collectors(test_targets),
    ]


__all__ = ["full_integrity_collectors", "touched_integrity_collectors"]
