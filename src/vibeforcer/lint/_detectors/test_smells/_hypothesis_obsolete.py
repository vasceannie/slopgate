"""Detectors for test-specific smells."""

from __future__ import annotations

import ast
from pathlib import Path
from vibeforcer.constants import (
    MISSING_IMPORT_PREVIEW_LIMIT,
    METADATA_FUNCTION,
)
from vibeforcer._types import ObjectDict
from vibeforcer.lint._baseline import Violation
from vibeforcer.lint._helpers import ParsedFile, project_root

from ._coverage_helpers import _metadata_int as _metadata_int
from ._integrity_index import TestIntegrityIndex as TestIntegrityIndex, build_test_integrity_index as build_test_integrity_index
from ._production_symbols import _HYPOTHESIS_NAME_TOKENS as _HYPOTHESIS_NAME_TOKENS, _ProductionSymbol as _ProductionSymbol, _module_names as _module_names, _package_roots as _package_roots, _production_symbols as _production_symbols, _production_test_inputs as _production_test_inputs, _reference_tokens_for_tree as _reference_tokens_for_tree, _symbol_is_referenced as _symbol_is_referenced


_HYPOTHESIS_PROPERTY_RULES = (
    (("parse", "serialize", "deserialize", "encode", "decode"), "round-trip / malformed-input contracts"),
    (("normalize", "canonical", "clean", "coerce"), "idempotence / canonicalization"),
    (("sort", "rank", "score", "order"), "ordering / monotonicity"),
    (("dedupe", "unique", "merge", "filter"), "dedup/filter/merge invariants"),
    (("bound", "limit", "clamp", "range", "validate"), "bounds / invalid-input rejection"),
)


def _hypothesis_properties(symbol: _ProductionSymbol) -> list[str]:
    text = f"{symbol.module}.{symbol.name}".lower()
    properties = [
        label
        for tokens, label in _HYPOTHESIS_PROPERTY_RULES
        if any(token in text for token in tokens)
    ]
    if properties:
        return properties
    if symbol.transform_score >= 3:
        return ["collection/string transform invariants"]
    if symbol.branch_score >= 4:
        return ["branch decision-table invariants"]
    return []


def _hypothesis_score(symbol: _ProductionSymbol) -> tuple[int, list[str], list[str]]:
    score = 0
    reasons: list[str] = []
    lowered = symbol.name.lower()
    name_hits = [token for token in _HYPOTHESIS_NAME_TOKENS if token in lowered]
    if name_hits:
        score += 2
        reasons.append(f"name suggests invariant work ({', '.join(name_hits[:3])})")
    if symbol.parameter_count >= 2:
        score += 2
        reasons.append(f"{symbol.parameter_count} inputs")
    elif symbol.parameter_count == 1:
        score += 1
        reasons.append("input domain")
    if symbol.branch_score >= 4:
        score += 2
        reasons.append(f"branch/validation paths={symbol.branch_score}")
    elif symbol.branch_score >= 2:
        score += 1
        reasons.append(f"branches={symbol.branch_score}")
    if symbol.transform_score >= 3:
        score += 2
        reasons.append(f"collection/string transforms={symbol.transform_score}")
    elif symbol.transform_score:
        score += 1
        reasons.append("data transformation")
    properties = _hypothesis_properties(symbol)
    if properties:
        reasons.append(f"candidate properties={'; '.join(properties[:2])}")
    return score, reasons, properties


def detect_hypothesis_candidates(
    src_files: list[Path] | list[ParsedFile] | None = None,
    test_files: list[Path] | list[ParsedFile] | None = None,
    *,
    index: TestIntegrityIndex | None = None,
) -> list[Violation]:
    """Find tested production functions likely to benefit from property-based tests."""
    if index is None:
        index = build_test_integrity_index(src_files, test_files)
    refs = index.test_reference_tokens
    hypothesis_refs = index.hypothesis_reference_tokens

    violations: list[Violation] = []
    for symbol in index.production_symbols:
        if symbol.kind != METADATA_FUNCTION or not _symbol_is_referenced(symbol, refs):
            continue
        if _symbol_is_referenced(symbol, hypothesis_refs):
            continue
        score, reasons, properties = _hypothesis_score(symbol)
        if score < 4:
            continue
        violations.append(
            Violation(
                rule="hypothesis-candidate",
                relative_path=symbol.relative_path,
                identifier=symbol.qualname,
                detail=(
                    f"line {symbol.lineno}: property_test_score={score}; "
                    f"reasons={'; '.join(reasons)}; no Hypothesis/given test reference"
                ),
                metadata={"property_test_score": score, "reasons": reasons, "candidate_properties": properties},
            )
        )
    return sorted(violations, key=lambda v: (-_metadata_int(v, "property_test_score"), v.relative_path, v.identifier))


def _project_module_path_exists(module: str) -> bool:
    module_path = project_root().joinpath(*module.split("."))
    return module_path.with_suffix(".py").is_file() or (module_path / "__init__.py").is_file()


def _missing_import_from_violation(
    node: ast.ImportFrom,
    pf: ParsedFile,
    roots: set[str],
    modules: set[str],
) -> Violation | None:
    if not node.module:
        return None
    module = node.module
    root = module.split(".", maxsplit=1)[0]
    if root not in roots or module in modules or _project_module_path_exists(module):
        return None
    imported_names = [alias.name for alias in node.names]
    return Violation(
        rule="obsolete-or-deprecated-test",
        relative_path=pf.rel,
        identifier=f"line-{node.lineno}",
        detail=(
            f"imports missing production module `{module}`; "
            f"imported={', '.join(imported_names[:MISSING_IMPORT_PREVIEW_LIMIT])}"
        ),
        metadata={"module": module, "line": node.lineno, "imported_names": imported_names},
    )


def _module_or_package_exists(module: str, modules: set[str]) -> bool:
    return (
        module in modules
        or any(existing.startswith(f"{module}.") for existing in modules)
        or _project_module_path_exists(module)
    )


def _missing_import_violations(
    node: ast.Import,
    pf: ParsedFile,
    roots: set[str],
    modules: set[str],
) -> list[Violation]:
    violations: list[Violation] = []
    for alias in node.names:
        module = alias.name
        root = module.split(".", maxsplit=1)[0]
        if root not in roots or _module_or_package_exists(module, modules):
            continue
        violations.append(
            Violation(
                rule="obsolete-or-deprecated-test",
                relative_path=pf.rel,
                identifier=f"line-{node.lineno}",
                detail=f"imports missing production module `{module}`",
                metadata={"module": module, "line": node.lineno, "imported_names": [module]},
            )
        )
    return violations


def _missing_production_imports(parsed_tests: list[ParsedFile], modules: set[str]) -> list[Violation]:
    roots = _package_roots(modules)
    violations: list[Violation] = []
    for pf in parsed_tests:
        for child in ast.walk(pf.tree):
            if isinstance(child, ast.ImportFrom):
                violation = _missing_import_from_violation(child, pf, roots, modules)
                if violation is not None:
                    violations.append(violation)
            elif isinstance(child, ast.Import):
                violations.extend(_missing_import_violations(child, pf, roots, modules))
    return violations


def detect_stale_test_references(
    src_files: list[Path] | list[ParsedFile] | None = None,
    test_files: list[Path] | list[ParsedFile] | None = None,
    *,
    index: TestIntegrityIndex | None = None,
) -> list[Violation]:
    """Find tests tied to missing modules or stale production APIs."""
    if index is None:
        index = build_test_integrity_index(src_files, test_files)
    modules = index.module_names
    violations = _missing_production_imports(index.parsed_tests, modules)
    deprecated_symbols = index.deprecated_symbols
    if not deprecated_symbols:
        return sorted(violations, key=lambda v: (v.relative_path, v.identifier))

    for pf in index.parsed_tests:
        refs = index.test_reference_tokens_by_rel.get(pf.rel, set())
        for symbol in deprecated_symbols:
            if not _symbol_is_referenced(symbol, refs):
                continue
            replacement = f"; replacement={symbol.replacement}" if symbol.replacement else ""
            metadata: ObjectDict = {"symbol": symbol.qualname, "production_path": symbol.relative_path}
            if symbol.replacement:
                metadata["replacement"] = symbol.replacement
            violations.append(
                Violation(
                    rule="obsolete-or-deprecated-test",
                    relative_path=pf.rel,
                    identifier=symbol.qualname,
                    detail=f"test references deprecated production {symbol.kind} `{symbol.qualname}`{replacement}",
                    metadata=metadata,
                )
            )
    return sorted(violations, key=lambda v: (v.relative_path, v.identifier))
