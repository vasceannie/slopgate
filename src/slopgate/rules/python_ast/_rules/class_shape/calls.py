"""Inspect AST call nodes to decide whether a function is a thin wrapper."""

from __future__ import annotations

import ast


def thin_wrapper_extract_single_call(stmt: ast.stmt) -> ast.Call | None:
    """Return the Call node if stmt is a single-statement Return/Expr call."""
    match stmt:
        case ast.Return(value=ast.Call() as call_node):
            return call_node
        case ast.Expr(value=ast.Call() as call_node):
            return call_node
        case _:
            pass
    return None


def thin_wrapper_attribute_name(node: ast.Attribute) -> str:
    """Return a dotted attribute path from an Attribute node."""
    parts: list[str] = [node.attr]
    current: ast.expr = node.value
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    else:
        return node.attr
    return ".".join(reversed(parts))


def thin_wrapper_call_target_name(call_node: ast.Call) -> str:
    """Return the callable name a thin wrapper delegates to."""
    func = call_node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return thin_wrapper_attribute_name(func)
    return "<unknown>"


def thin_wrapper_call_root_name(call_node: ast.Call) -> str | None:
    """Return the root Name of a call target, if one exists."""
    match call_node.func:
        case ast.Name(id=name):
            return name
        case ast.Attribute() as attr:
            current: ast.expr = attr.value
            while isinstance(current, ast.Attribute):
                current = current.value
            if isinstance(current, ast.Name):
                return current.id
        case _:
            pass
    return None


def thin_wrapper_has_self_or_cls_receiver(
    node: ast.FunctionDef | ast.AsyncFunctionDef, call_node: ast.Call
) -> bool:
    """Return True when the call is invoked on the function's self/cls arg."""
    if not node.args.args:
        return False
    receiver_name = node.args.args[0].arg
    if receiver_name not in {"self", "cls"}:
        return False
    return thin_wrapper_call_root_name(call_node) == receiver_name


def is_test_helper_path(path_value: str) -> bool:
    """Return True when path_value looks like a test helper module."""
    normalized = path_value.replace("\\", "/").lower()
    return (
        normalized.startswith("tests/")
        or "/tests/" in normalized
        or normalized.endswith("/conftest.py")
        or (normalized == "conftest.py")
    )


def is_exempt_cast_wrapper(call_node: ast.Call) -> bool:
    """Return True when the delegated call is typing.cast."""
    return isinstance(call_node.func, ast.Name) and call_node.func.id == "cast"


def is_exempt_test_helper_wrapper(
    node: ast.FunctionDef | ast.AsyncFunctionDef, call_node: ast.Call, path_value: str
) -> bool:
    """Return True when a test helper wrapper should be ignored."""
    if not is_test_helper_path(path_value):
        return False
    if isinstance(call_node.func, ast.Name) and call_node.func.id in {
        "cast",
        "dict",
        "list",
        "tuple",
    }:
        return True
    return thin_wrapper_has_self_or_cls_receiver(node, call_node)


def is_wrapper_candidate(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Return True when node is a non-dunder, undecorated single-statement function."""
    if node.name.startswith("__") and node.name.endswith("__"):
        return False
    if node.decorator_list:
        return False
    return len(node.body) == 1
