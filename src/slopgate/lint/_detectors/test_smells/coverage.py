"""Detectors for test-specific smells."""

from __future__ import annotations
import json
import xml.etree.ElementTree
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from slopgate.constants import PRODUCTION_SYMBOL_PREVIEW_LIMIT
from slopgate.lint._baseline import Violation
from slopgate.lint._config import get_config
from ._production_symbols import (
    COVERAGE_JSON_NAMES,
    COVERAGE_XML_NAMES,
    ProductionSymbol,
)


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


def coverage_percent_from_json_file(path: Path) -> dict[str, int]:
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
        percent = coverage_percent_from_summary(cast(dict[str, object], summary_obj))
        rel = coverage_rel_path(raw_path) if percent is not None else None
        if rel is not None and percent is not None:
            coverage[rel] = percent
    return coverage


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


def coverage_percent_from_xml_file(path: Path) -> dict[str, int]:
    try:
        root_node = xml.etree.ElementTree.parse(path).getroot()
    except (OSError, xml.etree.ElementTree.ParseError):
        return {}
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
    return coverage


def runtime_coverage_by_rel() -> tuple[str, dict[str, int]]:
    """Return existing runtime coverage report data if pytest-cov already wrote it.

    The linter intentionally does not run tests; it only consumes coverage.json or
    coverage.xml artifacts that are already present in the project root.
    """
    root = get_config().project_root
    for name in COVERAGE_JSON_NAMES:
        coverage = coverage_percent_from_json_file(root / name)
        if coverage:
            return (name, coverage)
    for name in COVERAGE_XML_NAMES:
        coverage = coverage_percent_from_xml_file(root / name)
        if coverage:
            return (name, coverage)
    return ("static-reference", {})


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


def runtime_coverage_violation(inputs: CoverageInputs) -> Violation | None:
    coverage = inputs.runtime_coverage.get(inputs.relative_path, 0)
    if coverage >= 80:
        return None
    detail = f"runtime_line_coverage={coverage}% from {inputs.coverage_source}; static_test_reference_coverage={inputs.static_coverage}% ({len(inputs.referenced)}/{len(inputs.symbols)} public symbols referenced); unreferenced={', '.join(inputs.missing[:PRODUCTION_SYMBOL_PREVIEW_LIMIT]) or 'none'}"
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


def static_coverage_violation(inputs: CoverageInputs) -> Violation | None:
    coverage = inputs.static_coverage
    if coverage >= 50:
        return None
    coverage_note = (
        "no coverage.json/coverage.xml found"
        if inputs.coverage_source == "static-reference"
        else f"not present in {inputs.coverage_source}"
    )
    detail = f"static_test_reference_coverage={coverage}% ({len(inputs.referenced)}/{len(inputs.symbols)} public symbols referenced); unreferenced={', '.join(inputs.missing[:PRODUCTION_SYMBOL_PREVIEW_LIMIT])}; {coverage_note}"
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


def coverage_violation(inputs: CoverageInputs) -> Violation | None:
    if inputs.runtime_coverage:
        if inputs.relative_path in inputs.runtime_coverage:
            return runtime_coverage_violation(inputs)
        return None
    return static_coverage_violation(inputs)
