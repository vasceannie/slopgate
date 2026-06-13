"""Batch lint detectors for hook rules with repository-file equivalents."""

from __future__ import annotations

import ast
import re
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from slopgate.lint._baseline import Violation
from slopgate.lint._config import get_config
from slopgate.lint._helpers import ParsedFile, ensure_parsed, find_source_files
from slopgate.lint._helpers.paths import relative_path
from slopgate.policy_defaults import RUNTIME_POLICY_DEFAULTS
from slopgate.rules.python_ast._rules.imports.helpers import (
    allowed_import_alias,
    import_alias_full_name,
    imported_modules,
    module_path_from_python_file,
    private_module_segments,
)

_FEATURE_ENVY_IGNORED_NAMES = frozenset(
    {
        "cls",
        "self",
        "np",
        "pd",
        "plt",
        "Path",
        "Optional",
        "Union",
        "List",
        "Dict",
        "Set",
        "Tuple",
    }
)
_FLAT_SIBLING_PATTERN = re.compile(r"^_?([a-z][a-z0-9]*)_[a-z0-9_]+\.pyi?$")
_FLAT_SIBLING_MIN_COUNT = 3
_FLAT_SIBLING_IGNORED_PREFIXES = frozenset({"test"})
_DEAD_CODE_TERMINATORS = (ast.Return, ast.Raise, ast.Break, ast.Continue)
_DEAD_CODE_BLOCK_OWNERS = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.Try,
    ast.With,
    ast.AsyncWith,
    ast.ExceptHandler,
)
_IMPORT_FANOUT_LIMIT = int(RUNTIME_POLICY_DEFAULTS["import_fanout_limit"])


def _parsed_files(files: Sequence[Path | ParsedFile] | None) -> list[ParsedFile]:
    return ensure_parsed(files, fallback=find_source_files())


def _function_parameters(node: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    names = {
        arg.arg
        for arg in (
            node.args.args + node.args.posonlyargs + node.args.kwonlyargs
        )
    }
    if node.args.vararg is not None:
        names.add(node.args.vararg.arg)
    if node.args.kwarg is not None:
        names.add(node.args.kwarg.arg)
    return names


def _attribute_root(node: ast.Attribute) -> str | None:
    current: ast.AST = node.value
    while isinstance(current, ast.Attribute):
        current = current.value
    return current.id if isinstance(current, ast.Name) else None


def _is_feature_envy_candidate(root: str, parameters: set[str]) -> bool:
    if root in parameters or root in _FEATURE_ENVY_IGNORED_NAMES:
        return False
    return root not in sys.stdlib_module_names


def _feature_envy_counts(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[Counter[str], int]:
    parameters = _function_parameters(node)
    counts: Counter[str] = Counter()
    for child in ast.walk(node):
        if not isinstance(child, ast.Attribute):
            continue
        root = _attribute_root(child)
        if root is not None and _is_feature_envy_candidate(root, parameters):
            counts[root] += 1
    return counts, counts.total()


def detect_feature_envy(
    files: Sequence[Path | ParsedFile] | None = None,
) -> list[Violation]:
    """Find functions whose attribute access is dominated by another object."""
    cfg = get_config()
    violations: list[Violation] = []
    for parsed_file in _parsed_files(files):
        for node in ast.walk(parsed_file.tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            counts, total = _feature_envy_counts(node)
            if total < cfg.feature_envy_min_accesses:
                continue
            for root, count in counts.items():
                if count / total > cfg.feature_envy_threshold:
                    violations.append(
                        Violation(
                            rule="feature-envy",
                            relative_path=parsed_file.rel,
                            identifier=node.name,
                            detail=f"{root}={count}/{total}",
                        )
                    )
                    break
    return violations


def _statement_blocks(node: ast.AST) -> list[list[ast.stmt]]:
    match node:
        case ast.FunctionDef() | ast.AsyncFunctionDef() | ast.With() | ast.AsyncWith():
            return [node.body]
        case ast.If() | ast.For() | ast.AsyncFor() | ast.While():
            return [node.body, node.orelse] if node.orelse else [node.body]
        case ast.Try():
            blocks = [node.body, *(handler.body for handler in node.handlers)]
            return [*blocks, node.orelse, node.finalbody]
        case ast.ExceptHandler():
            return [node.body]
        case _:
            return []


def _first_dead_code(blocks: list[list[ast.stmt]]) -> tuple[str, int] | None:
    for block in blocks:
        for index, stmt in enumerate(block[:-1]):
            if isinstance(stmt, _DEAD_CODE_TERMINATORS):
                dead_stmt = block[index + 1]
                return type(stmt).__name__.lower(), getattr(dead_stmt, "lineno", 0)
    return None


def detect_dead_code(
    files: Sequence[Path | ParsedFile] | None = None,
) -> list[Violation]:
    """Find unreachable statements after return, raise, break, or continue."""
    violations: list[Violation] = []
    for parsed_file in _parsed_files(files):
        for node in ast.walk(parsed_file.tree):
            if not isinstance(node, _DEAD_CODE_BLOCK_OWNERS):
                continue
            dead = _first_dead_code(_statement_blocks(node))
            if dead is None:
                continue
            cause, line_no = dead
            identifier = getattr(node, "name", f"line-{line_no}")
            violations.append(
                Violation(
                    rule="dead-code",
                    relative_path=parsed_file.rel,
                    identifier=identifier,
                    detail=f"after={cause}, line={line_no}",
                )
            )
    return violations


def _flat_sibling_prefix(name: str) -> str | None:
    match = _FLAT_SIBLING_PATTERN.match(name)
    if match is None:
        return None
    prefix = match.group(1)
    return None if prefix in _FLAT_SIBLING_IGNORED_PREFIXES else prefix


def _flat_sibling_names(directory: Path) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    if not directory.exists() or not directory.is_dir():
        return groups
    for child in directory.iterdir():
        if not child.is_file():
            continue
        prefix = _flat_sibling_prefix(child.name)
        if prefix is not None:
            groups.setdefault(prefix, []).append(child.name)
    return groups


def _has_same_named_package(directory: Path, prefix: str) -> bool:
    package = directory / prefix
    return package.is_dir() and (package / "__init__.py").exists()


def detect_flat_sibling_files(
    files: Sequence[Path | ParsedFile] | None = None,
) -> list[Violation]:
    """Find directories using flat prefix_*.py siblings instead of packages."""
    violations: list[Violation] = []
    checked_dirs: set[Path] = set()
    for parsed_file in _parsed_files(files):
        directory = parsed_file.path.parent
        if directory in checked_dirs:
            continue
        checked_dirs.add(directory)
        for prefix, names in _flat_sibling_names(directory).items():
            if len(names) < _FLAT_SIBLING_MIN_COUNT and not _has_same_named_package(
                directory, prefix
            ):
                continue
            first_name = sorted(names)[0]
            violations.append(
                Violation(
                    rule="flat-sibling-files",
                    relative_path=relative_path(directory / first_name),
                    identifier=prefix,
                    detail=f"files={len(names)}",
                )
            )
    return violations


def detect_import_fanout(
    files: Sequence[Path | ParsedFile] | None = None,
) -> list[Violation]:
    """Find from-import statements that pull too many names from one module."""
    violations: list[Violation] = []
    for parsed_file in _parsed_files(files):
        for node in ast.walk(parsed_file.tree):
            if not isinstance(node, ast.ImportFrom) or node.module is None:
                continue
            if len(node.names) <= _IMPORT_FANOUT_LIMIT:
                continue
            violations.append(
                Violation(
                    rule="import-fanout",
                    relative_path=parsed_file.rel,
                    identifier=node.module,
                    detail=f"imports={len(node.names)}",
                )
            )
    return violations


def detect_import_aliases(
    files: Sequence[Path | ParsedFile] | None = None,
) -> list[Violation]:
    """Find import aliases that are not canonical library conventions."""
    violations: list[Violation] = []
    for parsed_file in _parsed_files(files):
        for node in ast.walk(parsed_file.tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            for name in node.names:
                if allowed_import_alias(node, name):
                    continue
                alias = name.asname or name.name
                violations.append(
                    Violation(
                        rule="import-alias",
                        relative_path=parsed_file.rel,
                        identifier=alias,
                        detail=import_alias_full_name(node, name),
                    )
                )
    return violations


def _private_import_findings(parsed_file: ParsedFile) -> list[tuple[str, str]]:
    findings: list[tuple[str, str]] = []
    module_path = module_path_from_python_file(parsed_file.rel)
    if len(private_module_segments(module_path)) >= 2:
        findings.append((module_path, "module-file"))
    for node in ast.walk(parsed_file.tree):
        for line_no, module_name in imported_modules(node):
            if len(private_module_segments(module_name)) >= 2:
                findings.append((module_name, f"line={line_no}"))
    return findings


def detect_private_import_chains(
    files: Sequence[Path | ParsedFile] | None = None,
) -> list[Violation]:
    """Find modules or imports with stacked private implementation segments."""
    violations: list[Violation] = []
    for parsed_file in _parsed_files(files):
        for module_name, detail in _private_import_findings(parsed_file):
            violations.append(
                Violation(
                    rule="private-import-chain",
                    relative_path=parsed_file.rel,
                    identifier=module_name,
                    detail=detail,
                )
            )
    return violations
