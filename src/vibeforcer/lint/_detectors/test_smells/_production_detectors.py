"""Detectors for test-specific smells."""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path
from vibeforcer.constants import (
    INTEGRATION_SEAM_THRESHOLD,
    METADATA_FUNCTION,
    MISSING_IMPORT_PREVIEW_LIMIT,
)
from vibeforcer.lint._baseline import Violation
from vibeforcer.lint._helpers import ParsedFile

from ._assertion_core import _call_tail as _call_tail
from ._coverage_helpers import _CoverageInputs as _CoverageInputs, _coverage_violation as _coverage_violation, _metadata_int as _metadata_int, _runtime_coverage_by_rel as _runtime_coverage_by_rel
from ._integrity_index import TestIntegrityIndex as TestIntegrityIndex, build_test_integrity_index as build_test_integrity_index
from ._production_symbols import _INTEGRATION_HELPER_NAME_PREFIXES as _INTEGRATION_HELPER_NAME_PREFIXES, _INTEGRATION_SEAM_TOKENS as _INTEGRATION_SEAM_TOKENS, _INTEGRATION_UTILITY_MODULE_TOKENS as _INTEGRATION_UTILITY_MODULE_TOKENS, _INTEGRATION_UTILITY_NAME_TOKENS as _INTEGRATION_UTILITY_NAME_TOKENS, _ProductionSymbol as _ProductionSymbol, _integration_test_reference_tokens as _integration_test_reference_tokens, _production_symbols as _production_symbols, _production_test_inputs as _production_test_inputs, _symbol_is_referenced as _symbol_is_referenced


def detect_untested_production_code(
    src_files: list[Path] | list[ParsedFile] | None = None,
    test_files: list[Path] | list[ParsedFile] | None = None,
    *,
    index: TestIntegrityIndex | None = None,
) -> list[Violation]:
    """Find production modules with low runtime or static test coverage.

    If a coverage.json/coverage.xml report exists, findings are sorted by real
    runtime line coverage. Otherwise the detector falls back to static reference
    coverage by public symbol name and says so in the output.
    """
    if index is None:
        index = build_test_integrity_index(src_files, test_files)
    refs = index.test_reference_tokens
    coverage_source, runtime_coverage = _runtime_coverage_by_rel()
    by_path: dict[str, list[_ProductionSymbol]] = {}
    for symbol in index.production_symbols:
        by_path.setdefault(symbol.relative_path, []).append(symbol)

    violations: list[Violation] = []
    for rel, symbols in by_path.items():
        if not symbols:
            continue
        referenced = [symbol for symbol in symbols if _symbol_is_referenced(symbol, refs)]
        inputs = _CoverageInputs(
            relative_path=rel,
            symbols=symbols,
            referenced=referenced,
            missing=[symbol.name for symbol in symbols if symbol not in referenced],
            coverage_source=coverage_source,
            runtime_coverage=runtime_coverage,
        )
        violation = _coverage_violation(inputs)
        if violation is not None:
            violations.append(violation)
    return sorted(violations, key=lambda v: (_metadata_int(v, "coverage_percent"), v.relative_path))


def _production_call_sites(parsed_src: list[ParsedFile]) -> dict[str, list[str]]:
    symbols = _production_symbols(parsed_src)
    name_counts = Counter(symbol.name for symbol in symbols)
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
            tail = _call_tail(child)
            if tail not in unique_function_names:
                continue
            sites.setdefault(tail, set()).add(f"{pf.rel}:{child.lineno}")
    return {name: sorted(values) for name, values in sites.items() if values}


def _has_token(text: str, tokens: set[str]) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in tokens)


def _is_utility_or_trivial_helper(symbol: _ProductionSymbol) -> bool:
    lowered_name = symbol.name.lower()
    lowered_module = f".{symbol.module.lower()}"
    if lowered_name.startswith(_INTEGRATION_HELPER_NAME_PREFIXES):
        return True
    if lowered_name in _INTEGRATION_UTILITY_NAME_TOKENS:
        return True
    if any(token in lowered_module for token in _INTEGRATION_UTILITY_MODULE_TOKENS):
        return True
    if (
        symbol.branch_score <= 1
        and symbol.transform_score <= 1
        and symbol.parameter_count <= 2
        and not _has_token(f"{symbol.module}.{symbol.name}", _INTEGRATION_SEAM_TOKENS)
    ):
        return True
    return False


def _integration_seam_score(symbol: _ProductionSymbol, callers: int) -> tuple[int, list[str]]:
    score = callers
    reasons = [f"callers={callers}"]
    text = f"{symbol.module}.{symbol.name}".lower()
    seam_hits = [token for token in sorted(_INTEGRATION_SEAM_TOKENS) if token in text]
    if seam_hits:
        score += MISSING_IMPORT_PREVIEW_LIMIT
        reasons.append(f"seam-role={', '.join(seam_hits[:3])}")
    if symbol.branch_score >= 3:
        score += min(symbol.branch_score, 4)
        reasons.append(f"branches={symbol.branch_score}")
    if symbol.transform_score >= 2:
        score += min(symbol.transform_score, 4)
        reasons.append(f"transforms={symbol.transform_score}")
    if callers >= 5:
        score += 2
        reasons.append("high fan-in")
    if _is_utility_or_trivial_helper(symbol):
        score -= INTEGRATION_SEAM_THRESHOLD
        reasons.append("utility/trivial-helper discount")
    return score, reasons


def detect_missing_integration_tests(
    src_files: list[Path] | list[ParsedFile] | None = None,
    test_files: list[Path] | list[ParsedFile] | None = None,
    *,
    index: TestIntegrityIndex | None = None,
) -> list[Violation]:
    """Find reused production seams that lack integration/e2e references.

    The detector intentionally discounts tiny utilities/formatting helpers so the
    queue prioritizes dataflow, orchestration, parser, store, handler, API, and
    UI seams instead of high-fan-in leaf helpers such as markup/style functions.
    """
    if index is None:
        index = build_test_integrity_index(src_files, test_files)
    integration_refs = index.integration_test_reference_tokens
    call_sites = index.production_call_sites
    violations: list[Violation] = []
    for symbol in index.production_symbols:
        callers = len(call_sites.get(symbol.name, []))
        if (
            symbol.kind != METADATA_FUNCTION
            or callers < 2
            or not _has_token(f"{symbol.module}.{symbol.name}", _INTEGRATION_SEAM_TOKENS)
            or _is_utility_or_trivial_helper(symbol)
            or _symbol_is_referenced(symbol, integration_refs)
        ):
            continue
        seam_score, reasons = _integration_seam_score(symbol, callers)
        if seam_score < INTEGRATION_SEAM_THRESHOLD:
            continue
        violations.append(
            Violation(
                rule="missing-integration-test",
                relative_path=symbol.relative_path,
                identifier=symbol.qualname,
                detail=(
                    f"line {symbol.lineno}: production_callers={callers}; "
                    f"seam_score={seam_score}; reasons={'; '.join(reasons)}; "
                    f"no integration/e2e/pipeline test references `{symbol.name}`"
                ),
                metadata={
                    "caller_count": callers,
                    "seam_score": seam_score,
                    "symbol": symbol.qualname,
                    "caller_sites": call_sites.get(symbol.name, [])[:10],
                    "reasons": reasons,
                },
            )
        )
    return sorted(
        violations,
        key=lambda v: (-_metadata_int(v, "caller_count"), -_metadata_int(v, "seam_score"), v.relative_path, v.identifier),
    )
