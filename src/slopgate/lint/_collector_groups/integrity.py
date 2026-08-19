"""Test-integrity collector groups."""

from __future__ import annotations

from collections.abc import Callable

from slopgate.lint._collector_groups.integrity_specs import (
    lazy_integrity_index,
    touched_integrity_collector_specs,
)
from slopgate.lint._collector_groups.scheduling import CollectorSpec, execute_all
from slopgate.lint._collector_groups.types import CollectorResults
from slopgate.lint._detectors.test_smells import IntegrityIndex
from slopgate.lint._helpers import ParsedFile
from slopgate.lint.project_index import ProjectIndex


def touched_integrity_collectors(parsed_tests: list[ParsedFile]) -> CollectorResults:
    """Collect touched-test checks without building a suite-wide index."""
    return execute_all(touched_integrity_collector_specs(parsed_tests))


def full_integrity_collector_specs(
    parsed_src: list[ParsedFile],
    parsed_tests: list[ParsedFile],
    parsed_test_targets: list[ParsedFile] | None = None,
    project_index: ProjectIndex | None = None,
) -> list[CollectorSpec]:
    """Return deferred suite and touched integrity collectors."""
    from slopgate.lint._detectors.test_smells import (
        detect_hypothesis_candidates,
        detect_missing_integration_tests,
        detect_untested_production_code,
    )

    index = lazy_integrity_index(parsed_src, parsed_tests, project_index)
    test_targets = parsed_tests if parsed_test_targets is None else parsed_test_targets
    return [
        CollectorSpec(
            "untested-production-code",
            lambda: detect_untested_production_code(index=index()),
        ),
        CollectorSpec(
            "missing-integration-test",
            lambda: detect_missing_integration_tests(index=index()),
        ),
        CollectorSpec(
            "hypothesis-candidate",
            lambda: detect_hypothesis_candidates(index=index()),
        ),
        CollectorSpec(
            "obsolete-or-deprecated-test",
            lambda: _obsolete_hits(index, project_index),
        ),
        *touched_integrity_collector_specs(test_targets),
    ]


def _obsolete_hits(
    index: Callable[[], IntegrityIndex], project_index: ProjectIndex | None
):
    if project_index is not None and any(
        summary.facts.line_count for summary in project_index.files
    ):
        from slopgate.lint.project_index.integrity_facts import stale_reference_violations

        return stale_reference_violations(project_index)
    from slopgate.lint._detectors.test_smells import detect_stale_test_references

    return detect_stale_test_references(index=index())


def full_integrity_collectors(
    parsed_src: list[ParsedFile],
    parsed_tests: list[ParsedFile],
    *,
    parsed_test_targets: list[ParsedFile] | None = None,
) -> CollectorResults:
    """Collect bad-test-efficacy and holistic suite-quality indicators."""
    return execute_all(
        full_integrity_collector_specs(
            parsed_src, parsed_tests, parsed_test_targets
        )
    )


__all__ = ["full_integrity_collectors", "touched_integrity_collectors"]
