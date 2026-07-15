from __future__ import annotations

from slopgate.lint._detectors.test_smells import (
    CoverageInputs,
    ProductionSymbol,
    coverage_violation,
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


def test_coverage_violation_uses_runtime_entry_when_target_is_present() -> None:
    inputs = _inputs(
        runtime_coverage={"src/pkg/module.py": 0},
        referenced_count=2,
    )

    violation = coverage_violation(inputs)

    assert violation is not None, "explicit runtime zero should produce a violation"
    assert violation.detail.startswith("runtime_line_coverage=0% from coverage.xml"), (
        "present runtime entries should use runtime line coverage"
    )


def test_coverage_violation_falls_back_when_runtime_report_omits_target() -> None:
    inputs = _inputs(
        runtime_coverage={"src/pkg/covered.py": 100},
        referenced_count=0,
    )

    violation = coverage_violation(inputs)

    assert violation is not None, "omitted modules should receive static evaluation"
    assert "not present in coverage.xml" in violation.detail, (
        "static fallback should identify the partial runtime report"
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
    assert "no coverage.json/coverage.xml found" in violation.detail, (
        "static-only findings should explain that no runtime artifact was usable"
    )
