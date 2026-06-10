"""Detector for unnecessary thin wrappers.

A "thin wrapper" is a function whose body is a single ``return other_func(…)``
call that passes through all of its arguments unchanged.
"""

from __future__ import annotations

import ast
from collections.abc import Sequence
from pathlib import Path

from slopgate.lint._baseline import Violation
from slopgate.lint._config import get_config
from slopgate.lint._helpers import (
    ParsedFile,
    ensure_parsed,
    find_source_files,
    without_leading_docstring,
)


def _single_delegated_call(body: list[ast.stmt]) -> ast.Call | None:
    stmts = without_leading_docstring(body)
    if len(stmts) != 1:
        return None
    stmt = stmts[0]
    if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Call):
        return stmt.value
    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
        return stmt.value
    return None


def _delegatable_params(args: ast.arguments) -> set[str]:
    names = {a.arg for a in args.args}
    names |= {a.arg for a in args.posonlyargs}
    names |= {a.arg for a in args.kwonlyargs}
    names.discard("self")
    names.discard("cls")
    return names


def _is_passthrough_arg(arg: ast.expr, param_names: set[str]) -> bool:
    value = arg.value if isinstance(arg, ast.Starred) else arg
    return isinstance(value, ast.Name) and value.id in param_names


def _is_passthrough_keyword(keyword: ast.keyword, param_names: set[str]) -> bool:
    if keyword.arg is None:
        return True
    return isinstance(keyword.value, ast.Name) and keyword.value.id in param_names


def _passes_only_params(call: ast.Call, param_names: set[str]) -> bool:
    return all(_is_passthrough_arg(arg, param_names) for arg in call.args) and all(
        _is_passthrough_keyword(keyword, param_names) for keyword in call.keywords
    )


def _is_simple_delegation(
    func_node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> str | None:
    """If *func_node* is a thin wrapper, return the delegated call as a string.

    Returns ``None`` if the function does meaningful work beyond delegation.
    """
    call = _single_delegated_call(func_node.body)
    if call is None:
        return None

    callee = call_name(call)
    if not callee:
        return None

    if not _passes_only_params(call, _delegatable_params(func_node.args)):
        return None
    return callee


def call_name(call: ast.Call) -> str:
    """Extract a dotted name from a Call node."""
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        parts: list[str] = [func.attr]
        node = func.value
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if isinstance(node, ast.Name):
            parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


def detect_unnecessary_wrappers(
    files: Sequence[Path | ParsedFile] | None = None,
) -> list[Violation]:
    """Find thin wrapper functions that simply delegate to another call."""
    cfg = get_config()
    allowed = cfg.allowed_wrappers
    parsed = ensure_parsed(files, fallback=find_source_files())
    violations: list[Violation] = []

    for pf in parsed:
        for node in ast.walk(pf.tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            # Skip dunder methods, properties, and private overrides
            if node.name.startswith("__") and node.name.endswith("__"):
                continue
            # Skip decorated functions (often @property, @abstractmethod, etc.)
            if node.decorator_list:
                continue
            callee = _is_simple_delegation(node)
            if callee is None:
                continue
            if str((node.name, callee)) in allowed:
                continue
            violations.append(
                Violation(
                    rule="unnecessary-wrapper",
                    relative_path=pf.rel,
                    identifier=node.name,
                    detail=f"delegates to {callee}",
                )
            )

    return violations
