"""Detectors for test-specific smells."""

from __future__ import annotations
from pathlib import Path
from slopgate.constants import (
    INTEGRATION_SEAM_THRESHOLD,
    METADATA_FUNCTION,
    MISSING_IMPORT_PREVIEW_LIMIT,
)
from slopgate.lint._baseline import Violation
from slopgate.lint._helpers import ParsedFile
from ._coverage_helpers import (
    CoverageInputs,
    coverage_violation,
    metadata_int,
    runtime_coverage_by_rel,
)
from ._integrity_index import IntegrityIndex, build_test_integrity_index
from ._production_symbols import (
    INTEGRATION_HELPER_NAME_PREFIXES,
    INTEGRATION_SEAM_TOKENS,
    INTEGRATION_UTILITY_MODULE_TOKENS,
    INTEGRATION_UTILITY_NAME_TOKENS,
    ProductionSymbol,
    integration_test_reference_tokens,
    production_symbols,
    production_test_inputs,
    symbol_is_referenced,
)

__all__ = [
    "detect_untested_production_code",
    "detect_missing_integration_tests",
    "production_symbols",
    "production_test_inputs",
    "integration_test_reference_tokens",
]


def detect_untested_production_code(
    src_files: list[Path] | list[ParsedFile] | None = None,
    test_files: list[Path] | list[ParsedFile] | None = None,
    *,
    index: IntegrityIndex | None = None,
) -> list[Violation]:
    """Find production modules with low runtime or static test coverage.

    If a coverage.json/coverage.xml report exists, findings are sorted by real
    runtime line coverage. Otherwise the detector falls back to static reference
    coverage by public symbol name and says so in the output.
    """
    if index is None:
        index = build_test_integrity_index(src_files, test_files)
    refs = index.test_reference_tokens
    coverage_source, runtime_coverage = runtime_coverage_by_rel()
    by_path: dict[str, list[ProductionSymbol]] = {}
    for symbol in index.production_symbols:
        by_path.setdefault(symbol.relative_path, []).append(symbol)
    violations: list[Violation] = []
    for rel, symbols in by_path.items():
        if not symbols:
            continue
        referenced = [
            symbol for symbol in symbols if symbol_is_referenced(symbol, refs)
        ]
        inputs = CoverageInputs(
            relative_path=rel,
            symbols=symbols,
            referenced=referenced,
            missing=[symbol.name for symbol in symbols if symbol not in referenced],
            coverage_source=coverage_source,
            runtime_coverage=runtime_coverage,
        )
        violation = coverage_violation(inputs)
        if violation is not None:
            violations.append(violation)
    return sorted(
        violations, key=lambda v: (metadata_int(v, "coverage_percent"), v.relative_path)
    )


def has_token(text: str, tokens: set[str]) -> bool:
    lowered = text.lower()
    return any((token in lowered for token in tokens))


def is_utility_or_trivial_helper(symbol: ProductionSymbol) -> bool:
    lowered_name = symbol.name.lower()
    lowered_module = f".{symbol.module.lower()}"
    if lowered_name.startswith(INTEGRATION_HELPER_NAME_PREFIXES):
        return True
    if lowered_name in INTEGRATION_UTILITY_NAME_TOKENS:
        return True
    if any((token in lowered_module for token in INTEGRATION_UTILITY_MODULE_TOKENS)):
        return True
    if (
        symbol.branch_score <= 1
        and symbol.transform_score <= 1
        and (symbol.parameter_count <= 2)
        and (not has_token(f"{symbol.module}.{symbol.name}", INTEGRATION_SEAM_TOKENS))
    ):
        return True
    return False


def integration_seam_score(
    symbol: ProductionSymbol, callers: int
) -> tuple[int, list[str]]:
    score = callers
    reasons = [f"callers={callers}"]
    text = f"{symbol.module}.{symbol.name}".lower()
    seam_hits = [token for token in sorted(INTEGRATION_SEAM_TOKENS) if token in text]
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
    if is_utility_or_trivial_helper(symbol):
        score -= INTEGRATION_SEAM_THRESHOLD
        reasons.append("utility/trivial-helper discount")
    return (score, reasons)


def detect_missing_integration_tests(
    src_files: list[Path] | list[ParsedFile] | None = None,
    test_files: list[Path] | list[ParsedFile] | None = None,
    *,
    index: IntegrityIndex | None = None,
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
            or (
                not has_token(f"{symbol.module}.{symbol.name}", INTEGRATION_SEAM_TOKENS)
            )
            or is_utility_or_trivial_helper(symbol)
            or symbol_is_referenced(symbol, integration_refs)
        ):
            continue
        seam_score, reasons = integration_seam_score(symbol, callers)
        if seam_score < INTEGRATION_SEAM_THRESHOLD:
            continue
        violations.append(
            Violation(
                rule="missing-integration-test",
                relative_path=symbol.relative_path,
                identifier=symbol.qualname,
                detail=f"line {symbol.lineno}: production_callers={callers}; seam_score={seam_score}; reasons={'; '.join(reasons)}; no integration/e2e/pipeline test references `{symbol.name}`",
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
        key=lambda v: (
            -metadata_int(v, "caller_count"),
            -metadata_int(v, "seam_score"),
            v.relative_path,
            v.identifier,
        ),
    )
