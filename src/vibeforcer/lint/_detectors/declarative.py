"""Helpers for recognizing declarative code shapes in lint detectors."""

from __future__ import annotations

import ast


def should_skip_block_window(
    body: list[ast.stmt],
    window_indices: range,
    scope: str,
    canonical_import_indices: set[int],
) -> bool:
    """Return True when a statement window is declarative noise, not duplication."""
    if any(index in canonical_import_indices for index in window_indices):
        return True
    if all(_is_import_stmt(body[index]) for index in window_indices):
        return True
    return scope == "<module>" and all(
        is_declarative_constant_stmt(body[index]) for index in window_indices
    )


def _is_import_stmt(stmt: ast.stmt) -> bool:
    return isinstance(stmt, (ast.Import, ast.ImportFrom))


def is_constant_name(name: str) -> bool:
    """Return True when *name* follows module constant naming conventions."""
    bare = name.lstrip("_")
    return bool(bare) and bare.upper() == bare and any(char.isalpha() for char in bare)


def is_declarative_constant_value(node: ast.AST | None) -> bool:
    """Return True for literal-ish values safe to treat as declarative data."""
    if node is None:
        return True
    if isinstance(node, ast.Constant):
        return True
    if isinstance(node, ast.Name):
        return is_constant_name(node.id)
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        return all(is_declarative_constant_value(elt) for elt in node.elts)
    if isinstance(node, ast.Dict):
        return all(
            is_declarative_constant_value(key)
            and is_declarative_constant_value(value)
            for key, value in zip(node.keys, node.values, strict=True)
        )
    if isinstance(node, ast.UnaryOp):
        return is_declarative_constant_value(node.operand)
    return False


def is_declarative_constant_stmt(stmt: ast.stmt) -> bool:
    """Return True for simple module-level constant declarations."""
    if isinstance(stmt, ast.Assign):
        return _is_declarative_assign(stmt)
    if isinstance(stmt, ast.AnnAssign):
        return (
            isinstance(stmt.target, ast.Name)
            and is_constant_name(stmt.target.id)
            and is_declarative_constant_value(stmt.value)
        )
    return False


def _is_declarative_assign(stmt: ast.Assign) -> bool:
    targets = stmt.targets
    return bool(targets) and all(
        isinstance(target, ast.Name) and is_constant_name(target.id)
        for target in targets
    ) and is_declarative_constant_value(stmt.value)
