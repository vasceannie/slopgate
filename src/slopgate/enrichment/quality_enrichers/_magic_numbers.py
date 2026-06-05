"""Magic-number enrichment helpers."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import TYPE_CHECKING, cast

from slopgate.enrichment._helpers import (
    append_enrichment_message,
    relative_path,
    resolve_path,
    safe_parse,
    safe_read,
)
from slopgate.enrichment.quality_enrichers._models import (
    ImportableConstant,
    MagicNumberHint,
)
from slopgate.quality.constant_index import (
    build_project_constant_index,
    iter_constant_candidate_paths,
)

if TYPE_CHECKING:
    from slopgate.context import HookContext
    from slopgate.models import RuleFinding

_CONSTANT_MODULE_NAMES = {"constants", "config", "settings", "defaults"}
_SOURCE_ROOT_NAMES = {"src", "app"}
_MAX_IMPORTABLE_CONSTANTS = 5
_MAX_TRIGGERED_MAGIC_NUMBER_HINTS = 5
_MAGIC_NUMBER_MIN_ABSOLUTE = 200


def _find_constants_module(file_path: Path, root: Path) -> Path | None:
    index = build_project_constant_index(root)
    best = index.first_constants_file()
    if best is not None:
        return best

    search_dirs = (file_path.parent, file_path.parent.parent, root / "src")
    for base_dir in search_dirs:
        candidate = base_dir / "constants.py"
        if candidate.exists():
            return candidate
    return None


def _metadata_source_paths(finding: RuleFinding, root: Path) -> list[Path]:
    paths: list[Path] = []

    file_path = finding.metadata.get("file_path")
    if isinstance(file_path, str) and file_path:
        paths.append(resolve_path(file_path, root))

    hits = finding.metadata.get("hits")
    if isinstance(hits, list):
        raw_hits = cast(list[object], hits)
        for hit in raw_hits:
            if isinstance(hit, str) and hit:
                paths.append(resolve_path(hit, root))

    unique: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def _literal_constant_value(node: ast.AST | None) -> int | float | str | None:
    if isinstance(node, ast.Constant):
        value = node.value
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float, str)):
            return value
        return None
    if (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, ast.USub)
        and isinstance(node.operand, ast.Constant)
        and isinstance(node.operand.value, (int, float))
        and not isinstance(node.operand.value, bool)
    ):
        return -node.operand.value
    return None


def _format_constant_value(value: int | float | str) -> str:
    if isinstance(value, str):
        return repr(value)
    return str(value)


def _extract_importable_constants(path: Path) -> list[ImportableConstant]:
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


def _target_literal_values(ctx: HookContext) -> set[int | float | str]:
    values: set[int | float | str] = set()
    for target in ctx.content_targets:
        tree = safe_parse(target.content)
        if tree is None:
            continue
        for node in ast.walk(tree):
            value = _literal_constant_value(node)
            if value is not None:
                values.add(value)
    return values


def _parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    return {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }


def _uppercase_assignment_target(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> bool:
    parent = parents.get(node)
    if isinstance(parent, ast.UnaryOp):
        parent = parents.get(parent)
    if isinstance(parent, ast.Assign) and len(parent.targets) == 1:
        target = parent.targets[0]
        return isinstance(target, ast.Name) and target.id.isupper()
    if isinstance(parent, ast.AnnAssign):
        return isinstance(parent.target, ast.Name) and parent.target.id.isupper()
    return False


def _is_unary_numeric_operand(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> bool:
    parent = parents.get(node)
    return (
        isinstance(node, ast.Constant)
        and isinstance(parent, ast.UnaryOp)
        and isinstance(parent.op, ast.USub)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    )


def _is_triggered_magic_number(value: int | float) -> bool:
    return abs(value) >= _MAGIC_NUMBER_MIN_ABSOLUTE


def _triggered_magic_number_hints(ctx: HookContext) -> list[MagicNumberHint]:
    hints: list[MagicNumberHint] = []
    for target in ctx.content_targets:
        tree = safe_parse(target.content)
        if tree is None:
            continue
        parents = _parent_map(tree)
        target_path = target.path or "<proposed content>"
        for node in ast.walk(tree):
            value = _literal_constant_value(node)
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not _is_triggered_magic_number(value)
                or _uppercase_assignment_target(node, parents)
                or _is_unary_numeric_operand(node, parents)
            ):
                continue
            hints.append(
                MagicNumberHint(
                    path=target_path,
                    lineno=getattr(node, "lineno", 1),
                    value=value,
                )
            )
    return hints


def _append_triggered_magic_number_hints(
    extras: list[str], ctx: HookContext, root: Path
) -> None:
    hints = _triggered_magic_number_hints(ctx)[:_MAX_TRIGGERED_MAGIC_NUMBER_HINTS]
    if not hints:
        return
    rendered = []
    for hint in hints:
        path_text = relative_path(Path(hint.path), root) if hint.path else "<content>"
        rendered.append(f"{path_text} line {hint.lineno}: {hint.value}")
    extras.append("\nTriggered magic number candidates:")
    extras.extend(f"  {item}" for item in rendered)
    extras.append("Define/import constants first, then replace these literals before retrying.")


def _is_constant_module(path: Path) -> bool:
    return path.stem in _CONSTANT_MODULE_NAMES or path.name.endswith("_constants.py")


def _constant_file_candidates(constants_file: Path, root: Path) -> list[Path]:
    candidates: list[Path] = [constants_file]
    candidates.extend(iter_constant_candidate_paths(root))

    unique: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved in seen or not resolved.exists() or not _is_constant_module(resolved):
            continue
        seen.add(resolved)
        unique.append(resolved)
    return unique


def _module_name_for_import(constants_file: Path, root: Path) -> str:
    try:
        relative = constants_file.relative_to(root)
    except ValueError:
        return constants_file.stem

    parts = list(relative.with_suffix("").parts)
    if parts and parts[0] in _SOURCE_ROOT_NAMES:
        parts = parts[1:]
    return ".".join(parts) if parts else constants_file.stem


def _constant_search_root(ctx: HookContext) -> Path:
    """Return the project root that should own constants for hook feedback."""

    config_root = ctx.config.root
    if iter_constant_candidate_paths(config_root):
        return config_root
    return ctx.config.repo_root


def _append_importable_constant_hints(
    extras: list[str], constants_file: Path, root: Path, target_values: set[int | float | str]
) -> bool:
    constants_by_file: list[tuple[Path, list[ImportableConstant]]] = []
    for candidate in _constant_file_candidates(constants_file, root):
        constants = _extract_importable_constants(candidate)
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
        rendered_value = _format_constant_value(constant.value)
        extras.append(f"  {constant.name} = {rendered_value} ({relative}:{constant.lineno})")

    for path, constants in by_path.items():
        module = _module_name_for_import(path, root)
        names = ", ".join(constant.name for constant in constants)
        extras.append(f"  from {module} import {names}")
    if exact_matches:
        extras.append(
            "Import the existing constant from the cited path; do not create a duplicate, "
            "alias, or split-literal workaround."
        )
    return True


def enrich_magic_numbers(finding: RuleFinding, ctx: HookContext) -> None:
    """Enrich PY-QUALITY-010 with importable constants hints."""

    extras: list[str] = []
    target_values = _target_literal_values(ctx)
    root = _constant_search_root(ctx)
    _append_triggered_magic_number_hints(extras, ctx, root)
    for source_path in _metadata_source_paths(finding, root):
        constants_file = _find_constants_module(source_path, root)
        if constants_file is not None:
            relative = relative_path(constants_file, root)
            extras.append(f"\nProject constants module found: `{relative}`")
            _append_importable_constant_hints(
                extras, constants_file, root, target_values
            )
            break

    if not extras:
        extras.append(
            "\nDefine repeated literals in a constants/config module "
            + "instead of inline magic values. Do not split or concatenate "
            + "literal fragments to bypass the gate."
        )

    append_enrichment_message(finding, extras)
