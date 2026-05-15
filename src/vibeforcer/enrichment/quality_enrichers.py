"""Local enrichment helpers for quality-related rule IDs."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from typing import cast

from vibeforcer.enrichment._helpers import (
    append_enrichment_message,
    relative_path,
    resolve_path,
    safe_parse,
    safe_read,
)
from vibeforcer.quality.constant_index import build_project_constant_index

if TYPE_CHECKING:
    from vibeforcer.context import HookContext
    from vibeforcer.models import RuleFinding


_PATH_HINT_FILES = (
    "config.py",
    "settings.py",
    "paths.py",
    "constants.py",
    "env.py",
)

_PATH_HINT_TOKENS = ("PATH", "DIR", "ROOT", "BASE_PATH", "DATA_DIR")
_CONSTANT_MODULE_NAMES = {"constants", "config", "settings", "defaults"}
_CONSTANT_MODULE_PATTERNS = (
    "constants.py",
    "config.py",
    "settings.py",
    "defaults.py",
    "*_constants.py",
)
_SOURCE_ROOT_NAMES = {"src", "app"}
_MAX_IMPORTABLE_CONSTANTS = 5


@dataclass(frozen=True, slots=True)
class _ImportableConstant:
    name: str
    value: int | float | str
    path: Path
    lineno: int


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


def _extract_importable_constants(path: Path) -> list[_ImportableConstant]:
    source = safe_read(path, max_bytes=128_000)
    if not source:
        return []
    tree = safe_parse(source)
    if tree is None:
        return []

    constants: list[_ImportableConstant] = []
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
            _ImportableConstant(
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


def _candidate_constants_files(root: Path) -> list[Path]:
    paths: list[Path] = []
    seen: set[Path] = set()
    for pattern in _CONSTANT_MODULE_PATTERNS:
        for candidate in root.rglob(pattern):
            if not candidate.is_file() or candidate in seen:
                continue
            seen.add(candidate)
            paths.append(candidate)
    return sorted(paths)


def _is_constant_module(path: Path) -> bool:
    return path.stem in _CONSTANT_MODULE_NAMES or path.name.endswith("_constants.py")


def _constant_file_candidates(constants_file: Path, root: Path) -> list[Path]:
    candidates: list[Path] = [constants_file]
    candidates.extend(_candidate_constants_files(root))

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


def _append_importable_constant_hints(
    extras: list[str], constants_file: Path, root: Path, target_values: set[int | float | str]
) -> bool:
    constants_by_file: list[tuple[Path, list[_ImportableConstant]]] = []
    for candidate in _constant_file_candidates(constants_file, root):
        constants = _extract_importable_constants(candidate)
        if constants:
            constants_by_file.append((candidate, constants))

    if not constants_by_file:
        return False

    exact_matches: list[_ImportableConstant] = []
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

    by_path: dict[Path, list[_ImportableConstant]] = {}
    for constant in selected:
        by_path.setdefault(constant.path, []).append(constant)
        relative = relative_path(constant.path, root)
        rendered_value = _format_constant_value(constant.value)
        extras.append(f"  {constant.name} = {rendered_value} ({relative}:{constant.lineno})")

    for path, constants in by_path.items():
        module = _module_name_for_import(path, root)
        names = ", ".join(constant.name for constant in constants)
        extras.append(f"  from {module} import {names}")
    return True


def _path_hint_lines(content: str, max_lines: int = 4) -> list[str]:
    lines: list[str] = []
    for raw_line in content.splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if any(token in stripped for token in _PATH_HINT_TOKENS):
            lines.append(stripped)
            if len(lines) >= max_lines:
                break
    return lines


def _iter_path_config_candidates(root: Path) -> list[Path]:
    candidates: list[Path] = []
    for base_dir in (root / "src", root / "app", root / "config", root):
        for name in _PATH_HINT_FILES:
            candidate = base_dir / name
            if candidate.exists():
                candidates.append(candidate)
    return candidates


def enrich_magic_numbers(finding: RuleFinding, ctx: HookContext) -> None:
    """Enrich PY-QUALITY-010 with importable constants hints."""

    extras: list[str] = []
    target_values = _target_literal_values(ctx)
    for source_path in _metadata_source_paths(finding, ctx.config.root):
        constants_file = _find_constants_module(source_path, ctx.config.root)
        if constants_file is not None:
            relative = relative_path(constants_file, ctx.config.root)
            extras.append(f"\nProject constants module found: `{relative}`")
            _append_importable_constant_hints(
                extras, constants_file, ctx.config.root, target_values
            )
            break

    if not extras:
        extras.append(
            "\nDefine repeated literals in a constants/config module "
            + "instead of inline magic values."
        )

    append_enrichment_message(finding, extras)


def enrich_hardcoded_paths(finding: RuleFinding, ctx: HookContext) -> None:
    """Enrich PY-QUALITY-009 with central path-config hints."""

    extras: list[str] = []
    for candidate in _iter_path_config_candidates(ctx.config.root):
        content = safe_read(candidate, max_bytes=10_000)
        if not content:
            continue
        lines = _path_hint_lines(content)
        if not lines:
            continue

        relative = relative_path(candidate, ctx.config.root)
        extras.append(f"\nPath configuration found in `{relative}`:")
        extras.extend(f"  {line}" for line in lines)
        break

    if not extras:
        extras.append(
            "\nNo central path config found. Consider defining paths in a config module "
            + "or using environment variables."
        )

    append_enrichment_message(finding, extras)
