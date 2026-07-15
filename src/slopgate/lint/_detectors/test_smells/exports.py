"""Static Python export facts for test-integrity indexing."""

from __future__ import annotations

import ast
from dataclasses import dataclass

from slopgate.lint._helpers import ParsedFile
from .production_symbols import module_name_from_rel


SymbolKey = tuple[str, str]


@dataclass(frozen=True, slots=True)
class ExportFacts:
    """Deterministic ``__all__`` and package-facade re-export facts."""

    literal_all_by_module: dict[str, frozenset[str]]
    reference_names_by_symbol: dict[SymbolKey, tuple[str, ...]]


def _literal_string_collection(node: ast.AST) -> frozenset[str] | None:
    if not isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return None
    names: set[str] = set()
    for item in node.elts:
        if not isinstance(item, ast.Constant) or not isinstance(item.value, str):
            return None
        names.add(item.value)
    return frozenset(names)


def _literal_all(tree: ast.Module) -> frozenset[str] | None:
    resolved: frozenset[str] | None = None
    for node in tree.body:
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        if not any(
            isinstance(target, ast.Name) and target.id == "__all__"
            for target in targets
        ):
            continue
        resolved = (
            _literal_string_collection(node.value) if node.value is not None else None
        )
    return resolved


def _literal_all_by_module(
    parsed_src: list[ParsedFile], modules_by_rel: dict[str, str]
) -> dict[str, frozenset[str]]:
    result: dict[str, frozenset[str]] = {}
    for pf in parsed_src:
        module = modules_by_rel[pf.rel]
        literal_all = _literal_all(pf.tree)
        if module and literal_all is not None:
            result[module] = literal_all
    return result


def _relative_import_module(facade_module: str, node: ast.ImportFrom) -> str | None:
    if node.level < 1 or node.module is None:
        return None
    package_parts = facade_module.split(".") if facade_module else []
    keep = len(package_parts) - (node.level - 1)
    if keep < 0:
        return None
    return ".".join([*package_parts[:keep], node.module])


def _facade_reexports(
    pf: ParsedFile,
    facade_module: str,
    facade_all: frozenset[str] | None,
) -> dict[SymbolKey, set[str]]:
    references: dict[SymbolKey, set[str]] = {}
    for node in pf.tree.body:
        if not isinstance(node, ast.ImportFrom):
            continue
        implementation_module = _relative_import_module(facade_module, node)
        if implementation_module is None:
            continue
        for alias in node.names:
            public_name = alias.asname or alias.name
            if alias.name == "*" or (
                facade_all is not None and public_name not in facade_all
            ):
                continue
            references.setdefault((implementation_module, alias.name), set()).update(
                (public_name, f"{facade_module}.{public_name}")
            )
    return references


def _reexport_reference_names(
    parsed_src: list[ParsedFile],
    modules_by_rel: dict[str, str],
    literal_all_by_module: dict[str, frozenset[str]],
) -> dict[SymbolKey, tuple[str, ...]]:
    references: dict[SymbolKey, set[str]] = {}
    for pf in parsed_src:
        if not pf.rel.endswith("/__init__.py"):
            continue
        facade_module = modules_by_rel[pf.rel]
        for key, names in _facade_reexports(
            pf, facade_module, literal_all_by_module.get(facade_module)
        ).items():
            references.setdefault(key, set()).update(names)
    return {key: tuple(sorted(names)) for key, names in references.items()}


def build_export_facts(parsed_src: list[ParsedFile]) -> ExportFacts:
    """Build literal ``__all__`` and explicit package-facade re-export facts."""

    modules_by_rel = {pf.rel: module_name_from_rel(pf.rel) for pf in parsed_src}
    literal_all_by_module = _literal_all_by_module(parsed_src, modules_by_rel)
    return ExportFacts(
        literal_all_by_module=literal_all_by_module,
        reference_names_by_symbol=_reexport_reference_names(
            parsed_src, modules_by_rel, literal_all_by_module
        ),
    )


__all__: list[str] = []
