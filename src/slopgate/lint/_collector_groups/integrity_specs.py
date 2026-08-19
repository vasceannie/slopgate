"""Test-integrity collector specs."""

from __future__ import annotations

from collections.abc import Callable

from slopgate.lint._collector_groups.scheduling import CollectorSpec
from slopgate.lint._detectors.test_smells import IntegrityIndex
from slopgate.lint._helpers import ParsedFile
from slopgate.lint.project_index import ProjectIndex


def touched_integrity_collector_specs(
    parsed_tests: list[ParsedFile],
) -> list[CollectorSpec]:
    """Return deferred touched-test checks without a suite-wide index."""
    from slopgate.lint._detectors.test_smells import (
        detect_hand_built_test_payloads,
        detect_mock_theater,
        detect_mocked_integration_tests,
        detect_schema_bypasses,
        detect_weak_assertions,
    )

    return [
        CollectorSpec("weak-test-assertion", lambda: detect_weak_assertions(parsed_tests)),
        CollectorSpec("mock-theater", lambda: detect_mock_theater(parsed_tests)),
        CollectorSpec("schema-bypass-test-data", lambda: detect_schema_bypasses(parsed_tests)),
        CollectorSpec(
            "hand-built-test-payload",
            lambda: detect_hand_built_test_payloads(parsed_tests),
        ),
        CollectorSpec(
            "mocked-integration-test",
            lambda: detect_mocked_integration_tests(parsed_tests),
        ),
    ]


def lazy_integrity_index(
    parsed_src: list[ParsedFile],
    parsed_tests: list[ParsedFile],
    project_index: ProjectIndex | None = None,
) -> Callable[[], IntegrityIndex]:
    """Return a thunk that builds one shared IntegrityIndex on first use."""
    holder: list[IntegrityIndex] = []

    def integrity_index() -> IntegrityIndex:
        if not holder:
            holder.append(
                _materialize_integrity_index(parsed_src, parsed_tests, project_index)
            )
        return holder[0]

    return integrity_index


def _materialize_integrity_index(
    parsed_src: list[ParsedFile],
    parsed_tests: list[ParsedFile],
    project_index: ProjectIndex | None,
) -> IntegrityIndex:
    if project_index is not None and any(
        summary.facts.line_count for summary in project_index.files
    ):
        from slopgate.lint.project_index.integrity_store import (
            load_or_build_integrity_index,
        )

        return load_or_build_integrity_index(project_index)
    from slopgate.lint._detectors.test_smells import build_test_integrity_index

    return build_test_integrity_index(parsed_src, parsed_tests)
