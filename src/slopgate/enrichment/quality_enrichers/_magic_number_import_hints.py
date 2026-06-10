"""Importable-constant hint helpers for magic-number enrichment."""

from __future__ import annotations

import ast
from pathlib import Path

from slopgate.enrichment._helpers import relative_path, safe_parse, safe_read
from slopgate.enrichment.quality_enrichers._models import ImportableConstant
from slopgate.quality.constant_index import iter_constant_candidate_paths

_CONSTANT_MODULE_NAMES = {"constants", "config", "settings", "defaults"}
_SOURCE_ROOT_NAMES = {"src", "app"}
_MAX_IMPORTABLE_CONSTANTS = 5


def _literal_constant_value(node: ast.AST | None) -> int | float | str | None:
    if not isinstance(node, ast.Constant):
        return None
    value = node.value
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return value
    if isinstance(value, str):
        return value
    return None


def format_constant_value(value: int | float | str) -> str:
    if isinstance(value, str):
        return repr(value)
    return str(value)


def extract_importable_constants(path: Path) -> list[ImportableConstant]:
    source = safe_read(path, max_bytes=128_000)
    if not source:
        return []
    tree = safe_parse(source)
    if tree is None:
        return []

    constants: list[ImportableConstant] = []
    for node in tree.body:
        target_name: str | None = None
        value_node: ast.AST | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                target_name = target.id
                value_node = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target_name = node.target.id
            value_node = node.value

        value = _literal_constant_value(value_node)
        if target_name is None or value is None or not target_name.isupper():
            continue
        constants.append(
            ImportableConstant(
                name=target_name,
                value=value,
                path=path,
                lineno=getattr(node, "lineno", 1),
            )
        )
    return constants


def _is_constant_module(path: Path) -> bool:
    return path.stem in _CONSTANT_MODULE_NAMES or path.name.endswith("_constants.py")


def constant_file_candidates(constants_file: Path, root: Path) -> list[Path]:
    candidates: list[Path] = [constants_file]
    candidates.extend(iter_constant_candidate_paths(root))

    unique: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if (
            resolved in seen
            or not resolved.exists()
            or not _is_constant_module(resolved)
        ):
            continue
        seen.add(resolved)
        unique.append(resolved)
    return unique


def module_name_for_import(constants_file: Path, root: Path) -> str:
    try:
        relative = constants_file.relative_to(root)
    except ValueError:
        return constants_file.stem

    parts = list(relative.with_suffix("").parts)
    if parts and parts[0] in _SOURCE_ROOT_NAMES:
        parts = parts[1:]
    return ".".join(parts) if parts else constants_file.stem


def append_importable_constant_hints(
    extras: list[str],
    constants_file: Path,
    root: Path,
    target_values: set[int | float | str],
) -> bool:
    constants_by_file: list[tuple[Path, list[ImportableConstant]]] = []
    for candidate in constant_file_candidates(constants_file, root):
        constants = extract_importable_constants(candidate)
        if constants:
            constants_by_file.append((candidate, constants))

    if not constants_by_file:
        return False

    exact_matches: list[ImportableConstant] = []
    for _, constants in constants_by_file:
        exact_matches.extend(
            constant for constant in constants if constant.value in target_values
        )

    if exact_matches:
        selected = exact_matches[:_MAX_IMPORTABLE_CONSTANTS]
        extras.append("Exact constant match:")
    else:
        selected = constants_by_file[0][1][:_MAX_IMPORTABLE_CONSTANTS]
        extras.append("Nearby importable constants:")

    by_path: dict[Path, list[ImportableConstant]] = {}
    for constant in selected:
        by_path.setdefault(constant.path, []).append(constant)
        relative = relative_path(constant.path, root)
        rendered_value = format_constant_value(constant.value)
        extras.append(
            f"  {constant.name} = {rendered_value} ({relative}:{constant.lineno})"
        )

    for path, constants in by_path.items():
        module = module_name_for_import(path, root)
        names = ", ".join(constant.name for constant in constants)
        extras.append(f"  from {module} import {names}")
    if exact_matches:
        extras.append(
            "Import the existing constant from the cited path; do not create a duplicate, "
            "alias, or split-literal workaround."
        )
    return True
