"""Shared in-memory index for test-integrity detectors."""

from __future__ import annotations
import ast
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from slopgate.constants import METADATA_FUNCTION
from slopgate.lint._helpers import ParsedFile, ensure_parsed, find_test_files
from ._assertion_core import call_tail
from ._production_symbols import (
    ProductionSymbol,
    integration_test_reference_tokens,
    module_names,
    production_symbols,
    reference_tokens_for_tree,
    test_reference_tokens,
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
    symbols = production_symbols(parsed_src)
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
    )
