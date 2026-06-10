"""Helpers for recognizing declarative code shapes in lint detectors."""

from __future__ import annotations

import ast


_DECLARATIVE_CALL_NAMES = frozenset({"chr", "frozenset", "Path"})


def should_skip_block_window(
    body: list[ast.stmt],
    window_indices: range,
    scope: str,
    canonical_import_indices: set[int],
) -> bool:
    """Return True when a statement window is declarative noise, not duplication."""
    if any(index in canonical_import_indices for index in window_indices):
        return True
    if all(is_import_stmt(body[index]) for index in window_indices):
        return True
    if scope != "<module>":
        return False
    return _is_declarative_module_window([body[index] for index in window_indices])


def is_import_stmt(stmt: ast.stmt) -> bool:
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
            is_declarative_constant_value(key) and is_declarative_constant_value(value)
            for key, value in zip(node.keys, node.values, strict=True)
        )
    if isinstance(node, ast.UnaryOp):
        return is_declarative_constant_value(node.operand)
    if isinstance(node, ast.Call):
        return _is_declarative_constant_call(node)
    return False


def _call_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def _is_type_expr(node: ast.AST) -> bool:
    if isinstance(node, (ast.Name, ast.Attribute, ast.Subscript)):
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _is_type_expr(node.left) and _is_type_expr(node.right)
    return False


def _is_declarative_join_call(node: ast.Call) -> bool:
    if not isinstance(node.func, ast.Attribute):
        return False
    return (
        node.func.attr == "join"
        and is_declarative_constant_value(node.func.value)
        and len(node.args) == 1
        and not node.keywords
        and is_declarative_constant_value(node.args[0])
    )


def _is_declarative_cast_call(node: ast.Call) -> bool:
    return (
        _call_name(node) == "cast"
        and len(node.args) == 2
        and not node.keywords
        and _is_type_expr(node.args[0])
        and is_declarative_constant_value(node.args[1])
    )


def _is_declarative_constructor_call(node: ast.Call) -> bool:
    return (
        _call_name(node) in _DECLARATIVE_CALL_NAMES
        and all(is_declarative_constant_value(arg) for arg in node.args)
        and all(
            is_declarative_constant_value(keyword.value) for keyword in node.keywords
        )
    )


def _is_declarative_constant_call(node: ast.Call) -> bool:
    return (
        _is_declarative_constructor_call(node)
        or _is_declarative_join_call(node)
        or _is_declarative_cast_call(node)
    )


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


def _is_module_logger_stmt(stmt: ast.stmt) -> bool:
    """Return True for the standard module logger declaration scaffold."""
    if not isinstance(stmt, ast.Assign) or len(stmt.targets) != 1:
        return False
    target = stmt.targets[0]
    value = stmt.value
    return (
        isinstance(target, ast.Name)
        and target.id == "logger"
        and isinstance(value, ast.Call)
        and _call_name(value) in {"get_logger", "getLogger"}
        and len(value.args) == 1
        and isinstance(value.args[0], ast.Name)
        and value.args[0].id == "__name__"
        and not value.keywords
    )


def _is_declarative_module_window(statements: list[ast.stmt]) -> bool:
    """Return True for module-level declaration scaffolds, not behavior."""
    has_constant = False
    for stmt in statements:
        if is_declarative_constant_stmt(stmt):
            has_constant = True
            continue
        if _is_module_logger_stmt(stmt):
            continue
        return False
    return has_constant


def _is_declarative_assign(stmt: ast.Assign) -> bool:
    targets = stmt.targets
    return (
        bool(targets)
        and all(
            isinstance(target, ast.Name) and is_constant_name(target.id)
            for target in targets
        )
        and is_declarative_constant_value(stmt.value)
    )
