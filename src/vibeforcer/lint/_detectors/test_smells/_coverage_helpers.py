"""Detectors for test-specific smells."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from vibeforcer.constants import (
    PRODUCTION_SYMBOL_PREVIEW_LIMIT,
)
from vibeforcer.lint._baseline import Violation
from vibeforcer.lint._config import get_config

from ._production_symbols import _COVERAGE_JSON_NAMES as _COVERAGE_JSON_NAMES, _COVERAGE_XML_NAMES as _COVERAGE_XML_NAMES, _ProductionSymbol as _ProductionSymbol


def _metadata_int(violation: Violation, key: str) -> int:
    value = violation.metadata.get(key)
    return value if isinstance(value, int) else 0


def _coverage_rel_path(path_text: str) -> str | None:
    if not path_text:
        return None
    root = get_config().project_root
    path = Path(path_text)
    if not path.is_absolute():
        path = root / path
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (OSError, ValueError):
        normalized = path_text.replace("\\", "/")
        marker_index = normalized.find("src/")
        if marker_index >= 0:
            return normalized[marker_index:]
        return normalized


def _coverage_percent_from_summary(summary: dict[str, object]) -> int | None:
    percent_obj = summary.get("percent_covered")
    if isinstance(percent_obj, (int, float)):
        return int(round(percent_obj))
    display_obj = summary.get("percent_covered_display")
    if not isinstance(display_obj, str):
        return None
    try:
        return int(round(float(display_obj.rstrip("%"))))
    except ValueError:
        return None


def _coverage_percent_from_json_file(path: Path) -> dict[str, int]:
    try:
        data_obj: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data_obj, dict):
        return {}
    data = cast(dict[str, object], data_obj)
    files_obj = data.get("files")
    if not isinstance(files_obj, dict):
        return {}
    files = cast(dict[str, object], files_obj)
    coverage: dict[str, int] = {}
    for raw_path, raw_entry_obj in files.items():
        if not isinstance(raw_entry_obj, dict):
            continue
        raw_entry = cast(dict[str, object], raw_entry_obj)
        summary_obj = raw_entry.get("summary")
        if not isinstance(summary_obj, dict):
            continue
        percent = _coverage_percent_from_summary(cast(dict[str, object], summary_obj))
        rel = _coverage_rel_path(raw_path) if percent is not None else None
        if rel is not None and percent is not None:
            coverage[rel] = percent
    return coverage


def _coverage_percent_from_xml_file(path: Path) -> dict[str, int]:
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return {}
    coverage: dict[str, int] = {}
    for class_node in root.findall(".//class"):
        filename = class_node.attrib.get("filename", "")
        rel = _coverage_rel_path(filename)
        if rel is None:
            continue
        line_rate = class_node.attrib.get("line-rate")
        try:
            coverage[rel] = int(round(float(line_rate or "0") * 100))
        except ValueError:
            continue
    return coverage


def _runtime_coverage_by_rel() -> tuple[str, dict[str, int]]:
    """Return existing runtime coverage report data if pytest-cov already wrote it.

    The linter intentionally does not run tests; it only consumes coverage.json or
    coverage.xml artifacts that are already present in the project root.
    """
    root = get_config().project_root
    for name in _COVERAGE_JSON_NAMES:
        coverage = _coverage_percent_from_json_file(root / name)
        if coverage:
            return name, coverage
    for name in _COVERAGE_XML_NAMES:
        coverage = _coverage_percent_from_xml_file(root / name)
        if coverage:
            return name, coverage
    return "static-reference", {}


@dataclass(frozen=True, slots=True)
class _CoverageInputs:
    relative_path: str
    symbols: list[_ProductionSymbol]
    referenced: list[_ProductionSymbol]
    missing: list[str]
    coverage_source: str
    runtime_coverage: dict[str, int]

    @property
    def static_coverage(self) -> int:
        return int(round(100 * len(self.referenced) / len(self.symbols)))


def _runtime_coverage_violation(inputs: _CoverageInputs) -> Violation | None:
    coverage = inputs.runtime_coverage.get(inputs.relative_path, 0)
    if coverage >= 80:
        return None
    detail = (
        f"runtime_line_coverage={coverage}% from {inputs.coverage_source}; "
        f"static_test_reference_coverage={inputs.static_coverage}% "
        f"({len(inputs.referenced)}/{len(inputs.symbols)} public symbols referenced); "
        f"unreferenced={', '.join(inputs.missing[:PRODUCTION_SYMBOL_PREVIEW_LIMIT]) or 'none'}"
    )
    metadata = dict[str, object]()
    metadata["coverage_kind"] = "runtime-line"
    metadata["coverage_source"] = inputs.coverage_source
    metadata["coverage_percent"] = coverage
    metadata["static_reference_coverage_percent"] = inputs.static_coverage
    metadata["unreferenced_symbols"] = inputs.missing[:20]
    return Violation(
        rule="untested-production-code",
        relative_path=inputs.relative_path,
        identifier=f"coverage-{coverage:03d}",
        detail=detail,
        metadata=metadata,
    )


def _static_coverage_violation(inputs: _CoverageInputs) -> Violation | None:
    coverage = inputs.static_coverage
    if coverage >= 50:
        return None
    detail = (
        f"static_test_reference_coverage={coverage}% "
        f"({len(inputs.referenced)}/{len(inputs.symbols)} public symbols referenced); "
        f"unreferenced={', '.join(inputs.missing[:PRODUCTION_SYMBOL_PREVIEW_LIMIT])}; no coverage.json/coverage.xml found"
    )
    metadata = dict[str, object]()
    metadata["coverage_kind"] = "static-reference"
    metadata["coverage_percent"] = coverage
    metadata["unreferenced_symbols"] = inputs.missing[:20]
    return Violation(
        rule="untested-production-code",
        relative_path=inputs.relative_path,
        identifier=f"coverage-{coverage:03d}",
        detail=detail,
        metadata=metadata,
    )


def _coverage_violation(inputs: _CoverageInputs) -> Violation | None:
    if inputs.runtime_coverage:
        return _runtime_coverage_violation(inputs)
    return _static_coverage_violation(inputs)
