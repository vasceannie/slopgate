"""Detectors for test-specific smells."""

from __future__ import annotations
import json
import xml.etree.ElementTree
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, cast
from slopgate.constants import PRODUCTION_SYMBOL_PREVIEW_LIMIT
from slopgate.lint._baseline import Violation
from slopgate.lint._config import get_config
from .production_symbols import (
    COVERAGE_JSON_NAMES,
    COVERAGE_XML_NAMES,
    ProductionSymbol,
)


CoverageStatus = Literal["absent", "complete", "incomplete", "invalid"]
CoverageReason = Literal["malformed", "empty", "missing-modules"]
PUBLIC_API_DETAIL = "public API lacks coverage evidence"
ARTIFACT_DETAIL = "coverage artifact is incomplete or unusable"


@dataclass(frozen=True, slots=True)
class CoverageAssessment:
    status: CoverageStatus = "absent"
    source: str = "static-reference"
    coverage: dict[str, int] = field(default_factory=dict)
    expected_paths: tuple[str, ...] = ()
    missing_paths: tuple[str, ...] = ()
    reason: CoverageReason | None = None


@dataclass(frozen=True, slots=True)
class _CoverageParse:
    coverage: dict[str, int]
    malformed: bool = False


def metadata_int(violation: Violation, key: str) -> int:
    value = violation.metadata.get(key)
    return value if isinstance(value, int) else 0


def coverage_rel_path(path_text: str) -> str | None:
    if not path_text:
        return None
    root = get_config().project_root
    normalized_text = path_text.replace("\\", "/")
    path = Path(normalized_text)
    if not path.is_absolute():
        path = root / path
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        marker_index = normalized_text.find("src/")
        if marker_index >= 0:
            return normalized_text[marker_index:]
        return normalized_text


def coverage_percent_from_summary(summary: dict[str, object]) -> int | None:
    percent_obj = summary.get("percent_covered")
    if isinstance(percent_obj, (int, float)):
        return round(percent_obj)
    display_obj = summary.get("percent_covered_display")
    if not isinstance(display_obj, str):
        return None
    try:
        return round(float(display_obj.rstrip("%")))
    except ValueError:
        return None


def _coverage_from_json_file(path: Path) -> _CoverageParse:
    try:
        data_obj: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _CoverageParse({}, malformed=True)
    if not isinstance(data_obj, dict):
        return _CoverageParse({}, malformed=True)
    data = cast(dict[str, object], data_obj)
    files_obj = data.get("files")
    if not isinstance(files_obj, dict):
        return _CoverageParse({}, malformed=True)
    files = cast(dict[str, object], files_obj)
    coverage: dict[str, int] = {}
    for raw_path, raw_entry_obj in files.items():
        if not isinstance(raw_entry_obj, dict):
            continue
        raw_entry = cast(dict[str, object], raw_entry_obj)
        summary_obj = raw_entry.get("summary")
        if not isinstance(summary_obj, dict):
            continue
        percent = coverage_percent_from_summary(cast(dict[str, object], summary_obj))
        rel = coverage_rel_path(raw_path) if percent is not None else None
        if rel is not None and percent is not None:
            coverage[rel] = percent
    return _CoverageParse(coverage)


def coverage_percent_from_json_file(path: Path) -> dict[str, int]:
    return _coverage_from_json_file(path).coverage


def _xml_source_roots(root_node: xml.etree.ElementTree.Element) -> list[Path]:
    project_root = get_config().project_root
    roots: list[Path] = []
    for source_node in root_node.findall(".//source"):
        source_text = (source_node.text or "").strip()
        if not source_text:
            continue
        source_path = Path(source_text)
        if not source_path.is_absolute():
            source_path = project_root / source_path
        roots.append(source_path)
    return roots


def _coverage_xml_rel_paths(filename: str, source_roots: list[Path]) -> set[str]:
    rel_paths: set[str] = set()
    rel = coverage_rel_path(filename)
    if rel is not None:
        rel_paths.add(rel)
    if Path(filename).is_absolute():
        return rel_paths
    for source_root in source_roots:
        source_rel = coverage_rel_path((source_root / filename).as_posix())
        if source_rel is not None:
            rel_paths.add(source_rel)
    return rel_paths


def _coverage_from_xml_file(path: Path) -> _CoverageParse:
    try:
        root_node = xml.etree.ElementTree.parse(path).getroot()
    except (OSError, xml.etree.ElementTree.ParseError):
        return _CoverageParse({}, malformed=True)
    source_roots = _xml_source_roots(root_node)
    coverage: dict[str, int] = {}
    for class_node in root_node.findall(".//class"):
        filename = class_node.attrib.get("filename", "")
        rel_paths = _coverage_xml_rel_paths(filename, source_roots)
        if not rel_paths:
            continue
        line_rate = class_node.attrib.get("line-rate")
        try:
            percent = round(float(line_rate or "0") * 100)
        except ValueError:
            continue
        for rel in rel_paths:
            coverage[rel] = percent
    return _CoverageParse(coverage)


def coverage_percent_from_xml_file(path: Path) -> dict[str, int]:
    return _coverage_from_xml_file(path).coverage


def _assessment_for_artifact(
    name: str,
    parsed: _CoverageParse,
    expected_paths: set[str],
) -> CoverageAssessment:
    expected = tuple(sorted(expected_paths))
    if parsed.malformed:
        return CoverageAssessment(
            status="invalid",
            source=name,
            expected_paths=expected,
            missing_paths=expected,
            reason="malformed",
        )
    if not parsed.coverage:
        return CoverageAssessment(
            status="invalid",
            source=name,
            expected_paths=expected,
            missing_paths=expected,
            reason="empty",
        )
    missing = tuple(sorted(expected_paths - parsed.coverage.keys()))
    return CoverageAssessment(
        status="incomplete" if missing else "complete",
        source=name,
        coverage=parsed.coverage,
        expected_paths=expected,
        missing_paths=missing,
        reason="missing-modules" if missing else None,
    )


def runtime_coverage_by_rel(
    expected_paths: set[str] | None = None,
) -> CoverageAssessment:
    """Return existing runtime coverage report data if pytest-cov already wrote it.

    The linter intentionally does not run tests; it only consumes coverage.json or
    coverage.xml artifacts that are already present in the project root.
    """
    root = get_config().project_root
    for name in COVERAGE_JSON_NAMES:
        path = root / name
        if path.exists():
            return _assessment_for_artifact(
                name, _coverage_from_json_file(path), expected_paths or set()
            )
    for name in COVERAGE_XML_NAMES:
        path = root / name
        if path.exists():
            return _assessment_for_artifact(
                name, _coverage_from_xml_file(path), expected_paths or set()
            )
    return CoverageAssessment(expected_paths=tuple(sorted(expected_paths or set())))


def coverage_artifact_violation(
    assessment: CoverageAssessment,
) -> Violation | None:
    if assessment.status not in {"incomplete", "invalid"}:
        return None
    omitted_count = len(assessment.missing_paths)
    represented_count = len(assessment.expected_paths) - omitted_count
    return Violation(
        rule="coverage-artifact-incomplete",
        relative_path=assessment.source,
        identifier="coverage-artifact",
        detail=ARTIFACT_DETAIL,
        metadata={
            "reason": assessment.reason or "empty",
            "expected_count": len(assessment.expected_paths),
            "represented_count": represented_count,
            "omitted_count": omitted_count,
            "omitted_paths": assessment.missing_paths[:PRODUCTION_SYMBOL_PREVIEW_LIMIT],
        },
    )


@dataclass(frozen=True, slots=True)
class CoverageInputs:
    relative_path: str
    symbols: list[ProductionSymbol]
    referenced: list[ProductionSymbol]
    missing: list[str]
    coverage_source: str
    runtime_coverage: dict[str, int]

    @property
    def static_coverage(self) -> int:
        return round(100 * len(self.referenced) / len(self.symbols))


def _public_api_violation(
    inputs: CoverageInputs,
    coverage_kind: str,
    coverage: int,
    *,
    static_reference_coverage: int | None = None,
) -> Violation:
    metadata: dict[str, object] = {
        "coverage_kind": coverage_kind,
        "coverage_source": inputs.coverage_source,
        "coverage_percent": coverage,
    }
    if static_reference_coverage is not None:
        metadata["static_reference_coverage_percent"] = static_reference_coverage
    metadata["unreferenced_symbols"] = inputs.missing[:20]
    return Violation(
        rule="untested-public-api",
        relative_path=inputs.relative_path,
        identifier="public-api",
        detail=PUBLIC_API_DETAIL,
        metadata=metadata,
    )


def runtime_coverage_violation(inputs: CoverageInputs) -> Violation | None:
    coverage = inputs.runtime_coverage.get(inputs.relative_path, 0)
    if coverage >= 80:
        return None
    return _public_api_violation(
        inputs,
        "runtime-line",
        coverage,
        static_reference_coverage=inputs.static_coverage,
    )


def static_coverage_violation(inputs: CoverageInputs) -> Violation | None:
    coverage = inputs.static_coverage
    if coverage >= 50:
        return None
    return _public_api_violation(inputs, "static-reference", coverage)


def coverage_violation(inputs: CoverageInputs) -> Violation | None:
    """Use runtime coverage for represented modules and static coverage otherwise."""
    if inputs.relative_path in inputs.runtime_coverage:
        return runtime_coverage_violation(inputs)
    return static_coverage_violation(inputs)
