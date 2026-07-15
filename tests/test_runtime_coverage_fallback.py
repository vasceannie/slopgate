from __future__ import annotations

import importlib
import json
from pathlib import Path

from hypothesis import HealthCheck, given, settings, strategies

from slopgate.constants import PRODUCTION_SYMBOL_PREVIEW_LIMIT
from slopgate.lint._config import load_config

from slopgate.lint._detectors.test_smells import (
    CoverageAssessment,
    CoverageInputs,
    ProductionSymbol,
    coverage_violation,
    runtime_coverage_by_rel,
)


def _inputs(
    *, runtime_coverage: dict[str, int], referenced_count: int
) -> CoverageInputs:
    symbols = [
        ProductionSymbol(
            name=name,
            qualname=f"pkg.module.{name}",
            module="pkg.module",
            relative_path="src/pkg/module.py",
            lineno=1,
            kind="function",
            parameter_count=0,
            branch_score=0,
            transform_score=0,
            deprecated=False,
            replacement=None,
        )
        for name in ("covered", "missing")
    ]
    referenced = symbols[:referenced_count]
    return CoverageInputs(
        relative_path="src/pkg/module.py",
        symbols=symbols,
        referenced=referenced,
        missing=[symbol.name for symbol in symbols if symbol not in referenced],
        coverage_source="coverage.xml" if runtime_coverage else "static-reference",
        runtime_coverage=runtime_coverage,
    )


def _runtime_assessment(
    tmp_path: Path,
    expected_paths: set[str],
) -> CoverageAssessment:
    load_config(tmp_path)
    (tmp_path / "coverage.json").write_text(
        json.dumps(
            {
                "files": {
                    "src/pkg/covered.py": {
                        "summary": {"percent_covered": 100},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return runtime_coverage_by_rel(expected_paths)


def test_coverage_violation_uses_runtime_entry_when_target_is_present() -> None:
    inputs = _inputs(
        runtime_coverage={"src/pkg/module.py": 0},
        referenced_count=2,
    )

    violation = coverage_violation(inputs)

    assert violation is not None, "explicit runtime zero should produce a violation"
    assert (violation.rule, violation.identifier, violation.detail) == (
        "untested-public-api",
        "public-api",
        "public API lacks coverage evidence",
    ), "public API identity should not depend on mutable percentages"
    assert violation.metadata["coverage_kind"] == "runtime-line", (
        "present runtime entries should retain runtime evidence in metadata"
    )


def test_runtime_coverage_assessment_marks_omitted_modules_incomplete(
    tmp_path: Path,
) -> None:
    load_config(tmp_path)
    (tmp_path / "coverage.json").write_text(
        json.dumps(
            {
                "files": {
                    "src/pkg/covered.py": {
                        "summary": {"percent_covered": 100},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    coverage_module = importlib.import_module(
        "slopgate.lint._detectors.test_smells.coverage"
    )

    assessment = coverage_module.runtime_coverage_by_rel(
        {"src/pkg/covered.py", "src/pkg/omitted.py"}
    )

    assert assessment.status == "incomplete", (
        "present reports that omit expected modules should be rejected"
    )
    assert assessment.missing_paths == ("src/pkg/omitted.py",), (
        "omitted paths should be deterministic"
    )


def test_coverage_violation_allows_static_fallback_above_threshold() -> None:
    inputs = _inputs(
        runtime_coverage={"src/pkg/covered.py": 100},
        referenced_count=1,
    )

    assert coverage_violation(inputs) is None, (
        "omitted modules at the static threshold should pass"
    )


def test_coverage_violation_uses_static_fallback_without_runtime_report() -> None:
    inputs = _inputs(runtime_coverage={}, referenced_count=0)

    violation = coverage_violation(inputs)

    assert violation is not None, "missing runtime artifacts should use static coverage"
    assert violation.metadata["coverage_source"] == "static-reference", (
        "static-only findings should record that no runtime artifact was present"
    )


def test_runtime_coverage_assessment_uses_first_existing_artifact(
    tmp_path: Path,
) -> None:
    load_config(tmp_path)
    (tmp_path / "coverage.json").write_text("{broken", encoding="utf-8")
    (tmp_path / "coverage.xml").write_text(
        '<coverage><class filename="src/pkg/module.py" line-rate="1" /></coverage>',
        encoding="utf-8",
    )
    coverage_module = importlib.import_module(
        "slopgate.lint._detectors.test_smells.coverage"
    )

    assessment = coverage_module.runtime_coverage_by_rel({"src/pkg/module.py"})

    assert (assessment.status, assessment.source, assessment.reason) == (
        "invalid",
        "coverage.json",
        "malformed",
    ), "an earlier malformed artifact should not be hidden by later valid coverage"


def test_runtime_coverage_assessment_marks_empty_artifact_invalid(
    tmp_path: Path,
) -> None:
    load_config(tmp_path)
    (tmp_path / "coverage.json").write_text('{"files": {}}', encoding="utf-8")
    coverage_module = importlib.import_module(
        "slopgate.lint._detectors.test_smells.coverage"
    )

    assessment = coverage_module.runtime_coverage_by_rel({"src/pkg/module.py"})
    violation = coverage_module.coverage_artifact_violation(assessment)

    assert (assessment.status, assessment.reason) == ("invalid", "empty"), (
        "present artifacts without usable file entries should be invalid"
    )
    assert violation is not None, "invalid artifacts should produce one finding"
    assert violation.metadata == {
        "reason": "empty",
        "expected_count": 1,
        "represented_count": 0,
        "omitted_count": 1,
        "omitted_paths": ("src/pkg/module.py",),
    }, "invalid artifact metadata should describe every omitted expected module"


def test_runtime_coverage_assessment_marks_malformed_xml_invalid(
    tmp_path: Path,
) -> None:
    load_config(tmp_path)
    (tmp_path / "coverage.xml").write_text("<coverage>", encoding="utf-8")
    coverage_module = importlib.import_module(
        "slopgate.lint._detectors.test_smells.coverage"
    )

    assessment = coverage_module.runtime_coverage_by_rel({"src/pkg/module.py"})

    assert (assessment.status, assessment.source, assessment.reason) == (
        "invalid",
        "coverage.xml",
        "malformed",
    ), "malformed XML should produce a stable artifact reason"


def test_empty_earlier_artifact_precedes_later_valid_artifact(tmp_path: Path) -> None:
    load_config(tmp_path)
    (tmp_path / "coverage.json").write_text('{"files": {}}', encoding="utf-8")
    (tmp_path / "coverage.xml").write_text(
        '<coverage><class filename="src/pkg/module.py" line-rate="1" /></coverage>',
        encoding="utf-8",
    )
    coverage_module = importlib.import_module(
        "slopgate.lint._detectors.test_smells.coverage"
    )

    assessment = coverage_module.runtime_coverage_by_rel({"src/pkg/module.py"})

    assert (assessment.status, assessment.source, assessment.reason) == (
        "invalid",
        "coverage.json",
        "empty",
    ), "empty coverage.json should remain authoritative over later coverage.xml"


def test_artifact_violation_bounds_and_sorts_omitted_path_preview(
    tmp_path: Path,
) -> None:
    load_config(tmp_path)
    (tmp_path / "coverage.json").write_text(
        json.dumps(
            {"files": {"src/pkg/covered.py": {"summary": {"percent_covered": 100}}}}
        ),
        encoding="utf-8",
    )
    expected = {
        "src/pkg/covered.py",
        *(f"src/pkg/module_{index}.py" for index in range(20)),
    }
    coverage_module = importlib.import_module(
        "slopgate.lint._detectors.test_smells.coverage"
    )

    assessment = coverage_module.runtime_coverage_by_rel(expected)
    violation = coverage_module.coverage_artifact_violation(assessment)

    assert violation is not None, "partial artifacts should create one violation"
    omitted_paths = violation.metadata["omitted_paths"]
    assert (
        omitted_paths
        == tuple(sorted(expected - {"src/pkg/covered.py"}))[
            :PRODUCTION_SYMBOL_PREVIEW_LIMIT
        ]
    ), "omitted path previews should be deterministic and bounded"


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    strategies.sets(
        strategies.sampled_from(
            (
                "src/pkg/covered.py",
                "src/pkg/alpha.py",
                "src/pkg/beta.py",
                "src/pkg/gamma.py",
            )
        )
    )
)
def test_runtime_coverage_assessment_sorts_expected_and_missing_paths(
    tmp_path: Path,
    expected_paths: set[str],
) -> None:
    assessment = _runtime_assessment(tmp_path, expected_paths)

    assert assessment.missing_paths == tuple(
        sorted(expected_paths - {"src/pkg/covered.py"})
    ), "missing coverage paths should remain deterministic"
