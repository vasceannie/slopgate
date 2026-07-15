"""Export-aware production symbol selection."""

from __future__ import annotations

import ast

from slopgate.constants import METADATA_FUNCTION
from slopgate.lint._helpers import ParsedFile

from .exports import ExportFacts, build_export_facts
from .production_symbols import (
    ProductionSymbol,
    branch_score,
    module_name_from_rel,
    node_mentions_deprecated,
    parameter_count,
    replacement_hint,
    transform_score,
)


TopLevelDefinition = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef


def top_level_defs(tree: ast.Module) -> list[TopLevelDefinition]:
    return [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]


def _directly_public(
    module: str,
    name: str,
    literal_all: frozenset[str] | None,
) -> bool:
    if module.rsplit(".", maxsplit=1)[-1].startswith("_"):
        return False
    return name in literal_all if literal_all is not None else not name.startswith("_")


def _reference_names(
    module: str,
    name: str,
    facts: ExportFacts,
    *,
    directly_public: bool,
) -> tuple[str, ...]:
    names = set(facts.reference_names_by_symbol.get((module, name), ()))
    if directly_public:
        names.update((name, f"{module}.{name}"))
    return tuple(sorted(names))


def production_symbols(
    parsed_src: list[ParsedFile], export_facts: ExportFacts | None = None
) -> list[ProductionSymbol]:
    """Return top-level symbols exposed by Python naming and facade contracts."""

    facts = export_facts or build_export_facts(parsed_src)
    symbols: list[ProductionSymbol] = []
    for pf in parsed_src:
        module = module_name_from_rel(pf.rel)
        if not module:
            continue
        literal_all = facts.literal_all_by_module.get(module)
        for node in top_level_defs(pf.tree):
            direct = _directly_public(module, node.name, literal_all)
            names = _reference_names(module, node.name, facts, directly_public=direct)
            if names:
                symbols.append(
                    ProductionSymbol(
                        name=node.name,
                        qualname=f"{module}.{node.name}",
                        module=module,
                        relative_path=pf.rel,
                        lineno=node.lineno,
                        kind=(
                            "class"
                            if isinstance(node, ast.ClassDef)
                            else METADATA_FUNCTION
                        ),
                        parameter_count=parameter_count(node),
                        branch_score=branch_score(node),
                        transform_score=transform_score(node),
                        deprecated=node_mentions_deprecated(node),
                        replacement=replacement_hint(node),
                        reference_names=names,
                    )
                )
    return symbols


def internal_candidate_symbols(
    parsed_src: list[ParsedFile], export_facts: ExportFacts
) -> list[ProductionSymbol]:
    """Return unexported top-level definitions from underscore modules."""

    symbols: list[ProductionSymbol] = []
    for pf in parsed_src:
        module = module_name_from_rel(pf.rel)
        if not module or not module.rsplit(".", maxsplit=1)[-1].startswith("_"):
            continue
        for node in top_level_defs(pf.tree):
            if export_facts.reference_names_by_symbol.get((module, node.name)):
                continue
            names = tuple(sorted((node.name, f"{module}.{node.name}")))
            symbols.append(
                ProductionSymbol(
                    name=node.name,
                    qualname=f"{module}.{node.name}",
                    module=module,
                    relative_path=pf.rel,
                    lineno=node.lineno,
                    kind=(
                        "class" if isinstance(node, ast.ClassDef) else METADATA_FUNCTION
                    ),
                    parameter_count=parameter_count(node),
                    branch_score=branch_score(node),
                    transform_score=transform_score(node),
                    deprecated=node_mentions_deprecated(node),
                    replacement=replacement_hint(node),
                    reference_names=names,
                )
            )
    return symbols


def expected_coverage_paths(parsed_src: list[ParsedFile]) -> tuple[str, ...]:
    """Return indexed files containing top-level functions or classes."""

    return tuple(sorted(pf.rel for pf in parsed_src if top_level_defs(pf.tree)))


__all__ = [
    "expected_coverage_paths",
    "internal_candidate_symbols",
    "production_symbols",
    "top_level_defs",
]
