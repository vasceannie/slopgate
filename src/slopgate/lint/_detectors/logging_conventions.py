"""Detector for logging convention violations.

Ensures consistent use of a project-wide logger factory and variable name.
Flags direct ``logging.getLogger()`` calls and disallowed logger variable names.
"""
from __future__ import annotations

import ast
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from vibeforcer.lint._baseline import Violation
from vibeforcer.lint._config import get_config
from vibeforcer.lint._helpers import ParsedFile, ensure_parsed, find_source_files


@dataclass(frozen=True)
class _LoggerNameContext:
    rel_path: str
    disallowed: Sequence[str]
    expected: str


def _is_in_infrastructure(rel_path: str) -> bool:
    """Return True if the file is part of logging infrastructure (excluded)."""
    cfg = get_config()
    prefix = cfg.logging_infrastructure_path
    if not prefix:
        return False
    return rel_path.startswith(prefix)


def detect_direct_get_logger(
    files: Sequence[Path | ParsedFile] | None = None,
) -> list[Violation]:
    """Flag direct ``logging.getLogger(...)`` calls.

    Projects that define a custom logger factory should use it consistently
    instead of calling ``logging.getLogger`` directly.
    """
    cfg = get_config()
    if not cfg.logger_function:
        # No custom factory configured — nothing to enforce
        return []

    parsed = ensure_parsed(files, fallback=find_source_files())
    violations: list[Violation] = []

    for pf in parsed:
        if _is_in_infrastructure(pf.rel):
            continue
        for node in ast.walk(pf.tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            # logging.getLogger(...)
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "getLogger"
                and isinstance(func.value, ast.Name)
                and func.value.id == "logging"
            ):
                violations.append(
                    Violation(
                        rule="direct-get-logger",
                        relative_path=pf.rel,
                        identifier=f"L{node.lineno}",
                        detail=f"use {cfg.logger_function}() instead",
                    )
                )

    return violations


def detect_wrong_logger_name(
    files: Sequence[Path | ParsedFile] | None = None,
) -> list[Violation]:
    """Flag logger variables with disallowed names.

    The project should use a single, consistent variable name (e.g. ``logger``)
    for the module-level logger.
    """
    cfg = get_config()
    disallowed = cfg.disallowed_logger_names
    expected = cfg.logger_variable
    if not disallowed:
        return []

    parsed = ensure_parsed(files, fallback=find_source_files())
    violations: list[Violation] = []

    for pf in parsed:
        if _is_in_infrastructure(pf.rel):
            continue
        violations.extend(
            _collect_wrong_logger_name_violations(pf, list(disallowed), expected)
        )

    return violations


def _wrong_logger_name_violation(
    node: ast.Assign,
    target: ast.expr,
    context: _LoggerNameContext,
) -> Violation | None:
    if not isinstance(target, ast.Name):
        return None
    name = target.id
    if name not in context.disallowed:
        return None
    if not _is_logger_call(node.value):
        return None
    return Violation(
        rule="wrong-logger-name",
        relative_path=context.rel_path,
        identifier=f"L{node.lineno}",
        detail=f"'{name}' → use '{context.expected}'",
    )


def _wrong_logger_name_violations(
    node: ast.AST,
    context: _LoggerNameContext,
) -> list[Violation]:
    if not isinstance(node, ast.Assign):
        return []
    violations: list[Violation] = []
    for target in node.targets:
        violation = _wrong_logger_name_violation(
            node,
            target,
            context,
        )
        if violation is not None:
            violations.append(violation)
    return violations


def _collect_wrong_logger_name_violations(
    parsed_file: ParsedFile,
    disallowed: Sequence[str],
    expected: str,
) -> list[Violation]:
    context = _LoggerNameContext(parsed_file.rel, disallowed, expected)
    violations: list[Violation] = []
    for node in ast.walk(parsed_file.tree):
        violations.extend(_wrong_logger_name_violations(node, context))
    return violations


def _is_logger_call(node: ast.AST) -> bool:
    """Heuristic: is *node* a call that returns a logger?"""
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Attribute):
        if func.attr in ("getLogger", "get_logger"):
            return True
        # Custom logger factory (e.g. ``make_logger(...)``)
        cfg = get_config()
        if cfg.logger_function and func.attr == cfg.logger_function:
            return True
    if isinstance(func, ast.Name):
        cfg = get_config()
        if func.id in ("getLogger", "get_logger"):
            return True
        if cfg.logger_function and func.id == cfg.logger_function:
            return True
    return False
