"""Attach suite-integrity fields to per-file analysis facts."""

from __future__ import annotations

import ast

from dataclasses import replace
from typing import TYPE_CHECKING

from slopgate.constants import LANGUAGE_BY_SUFFIX
from slopgate.lint._helpers import ParsedFile
from slopgate.lint._helpers.models import FileParseError
from slopgate.lint.project_index.facts import (
    FileAnalysisFacts,
    ImportNodeFact,
    SymbolFact,
)
from slopgate.lint.project_index.models import ProjectIndex

if TYPE_CHECKING:
    from slopgate.lint._detectors.test_smells import ProductionSymbol


def attach_integrity_facts(
    parsed: ParsedFile, facts: FileAnalysisFacts
) -> FileAnalysisFacts:
    """Add production-symbol and reference-token facts used by suite collectors."""
    from slopgate.lint.project_index.fact_filter import wanted_fact_type
    from slopgate.lint.project_index.facts import FACT_TYPE_INTEGRITY

    if not wanted_fact_type(FACT_TYPE_INTEGRITY):
        return facts
    from slopgate.lint._detectors.test_smells import (
        integration_test_reference_tokens,
        production_symbols,
        reference_tokens_for_tree,
    )

    copied: list[SymbolFact] = []
    for symbol in production_symbols([parsed]):
        copied.append(
            SymbolFact(
                name=symbol.name,
                qualname=symbol.qualname,
                module=symbol.module,
                relative_path=symbol.relative_path,
                lineno=symbol.lineno,
                kind=symbol.kind,
                parameter_count=symbol.parameter_count,
                branch_score=symbol.branch_score,
                transform_score=symbol.transform_score,
                deprecated=symbol.deprecated,
                replacement=symbol.replacement,
            )
        )
    return replace(
        facts,
        production_symbols=tuple(copied),
        reference_tokens=tuple(sorted(reference_tokens_for_tree(parsed.tree))),
        integration_tokens=tuple(sorted(integration_test_reference_tokens([parsed]))),
        hypothesis_tokens=_hypothesis_tokens(parsed),
        call_tails=_call_tails(parsed),
        import_nodes=_import_nodes(parsed),
    )


def _hypothesis_tokens(parsed: ParsedFile) -> tuple[str, ...]:
    from slopgate.lint._detectors.test_smells import reference_tokens_for_tree

    source = "\n".join(parsed.lines).lower()
    if "hypothesis" not in source and "@given" not in source and "given(" not in source:
        return ()
    return tuple(sorted(reference_tokens_for_tree(parsed.tree)))


def _call_tails(parsed: ParsedFile) -> tuple[tuple[str, str], ...]:
    from slopgate.lint._detectors.test_smells import call_tail

    sites: list[tuple[str, str]] = []
    for child in ast.walk(parsed.tree):
        if isinstance(child, ast.Call) and (tail := call_tail(child)):
            sites.append((tail, f"{parsed.rel}:{child.lineno}"))
    return tuple(sites)


def _import_nodes(parsed: ParsedFile) -> tuple[ImportNodeFact, ...]:
    nodes: list[ImportNodeFact] = []
    for child in ast.walk(parsed.tree):
        if isinstance(child, ast.ImportFrom) and child.module:
            nodes.append(
                ImportNodeFact(
                    parsed.rel,
                    "importfrom",
                    child.module,
                    tuple(alias.name for alias in child.names),
                    child.lineno,
                )
            )
        elif isinstance(child, ast.Import):
            nodes.append(
                ImportNodeFact(
                    parsed.rel,
                    "import",
                    "",
                    tuple(alias.name for alias in child.names),
                    child.lineno,
                )
            )
    return tuple(nodes)


def integrity_index_from_project(index: ProjectIndex):
    """Rebuild the suite-integrity index from persisted per-file facts."""
    from slopgate.lint._detectors.test_smells import IntegrityIndex

    symbols = _symbols_from_index(index)
    tokens_by_rel = {
        summary.relative_path: set(summary.facts.reference_tokens)
        for summary in index.files
        if summary.kind == "test"
    }
    refs: set[str] = set()
    for tokens in tokens_by_rel.values():
        refs.update(tokens)
    return IntegrityIndex(
        parsed_src=[],
        parsed_tests=[],
        production_symbols=symbols,
        test_reference_tokens=refs,
        test_reference_tokens_by_rel=tokens_by_rel,
        integration_test_reference_tokens=_token_union(index, "integration_tokens"),
        production_call_sites=_call_sites_from_index(index, symbols),
        module_names=_source_modules(index),
        hypothesis_reference_tokens=_token_union(index, "hypothesis_tokens"),
        deprecated_symbols=[symbol for symbol in symbols if symbol.deprecated],
    )


def stale_reference_violations(index: ProjectIndex):
    """Rebuild stale test-reference hits from persisted import and token facts."""
    from slopgate.lint._baseline import Violation

    hits: list[Violation] = [
        *_stale_import_hits(index, _source_modules(index)),
        *_deprecated_hits(index),
    ]
    return sorted(hits, key=lambda item: (item.relative_path, item.identifier))


def _symbols_from_index(index: ProjectIndex):
    from slopgate.lint._detectors.test_smells import ProductionSymbol

    copied: list[ProductionSymbol] = []
    for summary in index.files:
        if summary.kind != "source":
            continue
        for symbol in summary.facts.production_symbols:
            copied.append(
                ProductionSymbol(
                    name=symbol.name,
                    qualname=symbol.qualname,
                    module=symbol.module,
                    relative_path=symbol.relative_path,
                    lineno=symbol.lineno,
                    kind=symbol.kind,
                    parameter_count=symbol.parameter_count,
                    branch_score=symbol.branch_score,
                    transform_score=symbol.transform_score,
                    deprecated=symbol.deprecated,
                    replacement=symbol.replacement,
                )
            )
    return copied


def _token_union(index: ProjectIndex, field: str) -> set[str]:
    tokens: set[str] = set()
    for summary in index.files:
        if summary.kind == "test":
            tokens.update(getattr(summary.facts, field))
    return tokens


def _source_modules(index: ProjectIndex) -> set[str]:
    return {
        summary.facts.module_name
        for summary in index.files
        if summary.kind == "source" and summary.facts.module_name
    }


def _call_sites_from_index(
    index: ProjectIndex, symbols: list[ProductionSymbol]
) -> dict[str, list[str]]:
    from collections import Counter

    from slopgate.constants import METADATA_FUNCTION

    function_counts = Counter(
        symbol.name for symbol in symbols if symbol.kind == METADATA_FUNCTION
    )
    unique = {name for name, count in function_counts.items() if count == 1}
    sites: dict[str, set[str]] = {name: set() for name in unique}
    for summary in index.files:
        if summary.kind != "source":
            continue
        for tail, location in summary.facts.call_tails:
            if tail in unique:
                sites[tail].add(location)
    return {name: sorted(values) for name, values in sites.items() if values}


def _stale_import_hits(index: ProjectIndex, modules: set[str]):
    from slopgate.lint._baseline import Violation
    from slopgate.lint._detectors.test_smells import package_roots

    roots = package_roots(modules)
    hits: list[Violation] = []
    for summary in index.files:
        if summary.kind != "test":
            continue
        for node in summary.facts.import_nodes:
            hits.extend(_import_node_hits(node, roots, modules))
    return hits


def _import_node_hits(node: ImportNodeFact, roots: set[str], modules: set[str]):
    from slopgate.constants import MISSING_IMPORT_PREVIEW_LIMIT
    from slopgate.lint._baseline import Violation
    from slopgate.lint._detectors.test_smells import module_or_package_exists

    if node.kind == "importfrom":
        root = node.module.split(".", maxsplit=1)[0]
        if root not in roots or node.module in modules or _module_path_exists(node.module):
            return []
        preview = ", ".join(node.names[:MISSING_IMPORT_PREVIEW_LIMIT])
        return [
            Violation(
                rule="obsolete-or-deprecated-test",
                relative_path=node.relative_path,
                identifier=f"line-{node.lineno}",
                detail=(
                    f"imports missing production module `{node.module}`; imported={preview}"
                ),
                metadata={
                    "module": node.module,
                    tuple(FileParseError.__dataclass_fields__)[2]: node.lineno,
                    "imported_names": list(node.names),
                },
            )
        ]
    hits: list[Violation] = []
    for name in node.names:
        root = name.split(".", maxsplit=1)[0]
        if root not in roots or module_or_package_exists(name, modules):
            continue
        hits.append(
            Violation(
                rule="obsolete-or-deprecated-test",
                relative_path=node.relative_path,
                identifier=f"line-{node.lineno}",
                detail=f"imports missing production module `{name}`",
                metadata={"module": name, tuple(FileParseError.__dataclass_fields__)[2]: node.lineno, "imported_names": [name]},
            )
        )
    return hits


def _deprecated_hits(index: ProjectIndex):
    from slopgate.lint._baseline import Violation

    deprecated = [symbol for symbol in _symbols_from_index(index) if symbol.deprecated]
    if not deprecated:
        return []
    hits: list[Violation] = []
    for summary in index.files:
        if summary.kind != "test":
            continue
        refs = set(summary.facts.reference_tokens)
        hits.extend(_deprecated_for_refs(summary.relative_path, refs, deprecated))
    return hits


def _deprecated_for_refs(relative: str, refs: set[str], deprecated: list[ProductionSymbol]):
    from slopgate.lint._baseline import Violation
    from slopgate.lint._detectors.test_smells import symbol_is_referenced

    hits: list[Violation] = []
    for symbol in deprecated:
        if not symbol_is_referenced(symbol, refs):
            continue
        suffix = f"; replacement={symbol.replacement}" if symbol.replacement else ""
        metadata: dict[str, object] = {
            "symbol": symbol.qualname,
            "production_path": symbol.relative_path,
        }
        if symbol.replacement:
            metadata["replacement"] = symbol.replacement
        hits.append(
            Violation(
                rule="obsolete-or-deprecated-test",
                relative_path=relative,
                identifier=symbol.qualname,
                detail=(
                    f"test references deprecated production {symbol.kind} "
                    f"`{symbol.qualname}`{suffix}"
                ),
                metadata=metadata,
            )
        )
    return hits


def _module_path_exists(module: str) -> bool:
    from slopgate.lint._helpers import project_root

    path = project_root().joinpath(*module.split("."))
    return path.with_suffix(next(iter(LANGUAGE_BY_SUFFIX))).is_file() or (
        path / "__init__.py"
    ).is_file()
