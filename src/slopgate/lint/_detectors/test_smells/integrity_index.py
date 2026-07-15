"""Shared in-memory index for test-integrity detectors."""

from __future__ import annotations
import ast
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from slopgate.constants import METADATA_FUNCTION
from slopgate.lint._helpers import ParsedFile, ensure_parsed, find_test_files
from ._assertion_core import call_tail
from .coverage import CoverageAssessment, runtime_coverage_by_rel
from .exports import ExportFacts, build_export_facts
from .production_symbols import (
    ProductionSymbol,
    integration_test_reference_tokens,
    module_names,
    reference_tokens_for_tree,
    test_reference_tokens,
)
from .public_symbols import (
    expected_coverage_paths,
    internal_candidate_symbols,
    production_symbols,
)


@dataclass(frozen=True)
class IntegrityIndex:
    """Reusable facts shared by holistic test-integrity detectors."""

    parsed_src: list[ParsedFile]
    parsed_tests: list[ParsedFile]
    production_symbols: list[ProductionSymbol]
    test_reference_tokens: set[str]
    test_reference_tokens_by_rel: dict[str, set[str]]
    integration_test_reference_tokens: set[str]
    production_call_sites: dict[str, list[str]]
    module_names: set[str]
    hypothesis_reference_tokens: set[str]
    deprecated_symbols: list[ProductionSymbol]
    export_facts: ExportFacts = field(default_factory=lambda: ExportFacts({}, {}))
    internal_candidate_symbols: list[ProductionSymbol] = field(default_factory=list)
    internal_call_sites: dict[str, list[str]] = field(default_factory=dict)
    production_reference_tokens: set[str] = field(default_factory=set)
    expected_coverage_paths: tuple[str, ...] = ()
    coverage_assessment: CoverageAssessment = field(default_factory=CoverageAssessment)


def _production_call_sites_from_symbols(
    parsed_src: list[ParsedFile], symbols: list[ProductionSymbol]
) -> dict[str, list[str]]:
    name_counts = Counter((symbol.name for symbol in symbols))
    unique_function_names = {
        symbol.name
        for symbol in symbols
        if symbol.kind == METADATA_FUNCTION and name_counts[symbol.name] == 1
    }
    sites: dict[str, set[str]] = {name: set() for name in unique_function_names}
    for pf in parsed_src:
        for child in ast.walk(pf.tree):
            if not isinstance(child, ast.Call):
                continue
            tail = call_tail(child)
            if tail not in unique_function_names:
                continue
            sites.setdefault(tail, set()).add(f"{pf.rel}:{child.lineno}")
    return {name: sorted(values) for name, values in sites.items() if values}


def _hypothesis_reference_tokens(parsed_tests: list[ParsedFile]) -> set[str]:
    refs: set[str] = set()
    for pf in parsed_tests:
        source = "\n".join(pf.lines).lower()
        if (
            "hypothesis" not in source
            and "@given" not in source
            and ("given(" not in source)
        ):
            continue
        refs.update(reference_tokens_for_tree(pf.tree))
    return refs


def build_test_integrity_index(
    src_files: list[Path] | list[ParsedFile] | None = None,
    test_files: list[Path] | list[ParsedFile] | None = None,
) -> IntegrityIndex:
    """Build reusable facts for all holistic test-integrity detectors."""
    parsed_src = ensure_parsed(src_files, fallback=[])
    parsed_tests = ensure_parsed(test_files, fallback=find_test_files())
    export_facts = build_export_facts(parsed_src)
    symbols = production_symbols(parsed_src, export_facts)
    internal_symbols = internal_candidate_symbols(parsed_src, export_facts)
    expected_paths = expected_coverage_paths(parsed_src)
    refs_by_rel = {pf.rel: reference_tokens_for_tree(pf.tree) for pf in parsed_tests}
    refs = test_reference_tokens(parsed_tests)
    return IntegrityIndex(
        parsed_src=parsed_src,
        parsed_tests=parsed_tests,
        production_symbols=symbols,
        test_reference_tokens=refs,
        test_reference_tokens_by_rel=refs_by_rel,
        integration_test_reference_tokens=integration_test_reference_tokens(
            parsed_tests
        ),
        production_call_sites=_production_call_sites_from_symbols(parsed_src, symbols),
        module_names=module_names(parsed_src),
        hypothesis_reference_tokens=_hypothesis_reference_tokens(parsed_tests),
        deprecated_symbols=[symbol for symbol in symbols if symbol.deprecated],
        export_facts=export_facts,
        internal_candidate_symbols=internal_symbols,
        internal_call_sites=_production_call_sites_from_symbols(
            parsed_src, internal_symbols
        ),
        production_reference_tokens={
            token for pf in parsed_src for token in reference_tokens_for_tree(pf.tree)
        },
        expected_coverage_paths=expected_paths,
        coverage_assessment=runtime_coverage_by_rel(set(expected_paths)),
    )
