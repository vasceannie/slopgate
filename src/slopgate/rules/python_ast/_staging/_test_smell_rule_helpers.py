"""Shared AST helpers for staged pytest smell hook rules."""

from __future__ import annotations

import ast
from collections import deque
from collections.abc import Iterator
from typing import TYPE_CHECKING, TypeGuard

from slopgate.rules.python_ast._helpers import parse_module

if TYPE_CHECKING:
    from slopgate.context import HookContext

ASSERT_PATTERNS = frozenset(
    {
        "assert",
        "assertEqual",
        "assertRaises",
        "assertIn",
        "assertTrue",
        "assertFalse",
        "assertIsNone",
        "assertIsNotNone",
        "assertAlmostEqual",
        "assertGreater",
        "assertLess",
        "assertRegex",
        "assertNotEqual",
        "assertIs",
        "assert_called",
        "assert_called_once",
        "assert_called_with",
        "assert_called_once_with",
        "assert_not_called",
        "assert_any_call",
        "assert_has_calls",
    }
)


def is_test_function(
    node: ast.AST,
) -> TypeGuard[ast.FunctionDef | ast.AsyncFunctionDef]:
    """True if node is a test function (starts with test_)."""
    return isinstance(
        node, (ast.FunctionDef, ast.AsyncFunctionDef)
    ) and node.name.startswith("test_")


def is_test_file(path: str) -> bool:
    """Heuristic: is this path likely a test file?"""
    p = path.replace("\\", "/").lower()
    return "test" in p.split("/")[-1].split(".")[0].split("_") or "test_" in p


def contains_assertion(node: ast.AST) -> bool:
    """True if the subtree contains any assertion."""
    for child in ast.walk(node):
        if isinstance(child, ast.Assert):
            return True
        if isinstance(child, ast.Call):
            func = child.func
            name = ""
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = func.attr
            if name in ASSERT_PATTERNS:
                return True
    return False


def walk_skip_nested_funcs(node: ast.AST) -> Iterator[ast.AST]:
    """Walk AST without descending into nested FunctionDef/AsyncFunctionDef."""
    todo = deque(ast.iter_child_nodes(node))
    while todo:
        child = todo.popleft()
        yield child
        if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            todo.extend(ast.iter_child_nodes(child))


def is_type_checking_block(node: ast.AST) -> bool:
    """True if node is `if TYPE_CHECKING:` or `if typing.TYPE_CHECKING:`."""
    match node:
        case ast.If(test=ast.Name(id="TYPE_CHECKING")):
            return True
        case ast.If(
            test=ast.Attribute(attr="TYPE_CHECKING", value=ast.Name(id="typing"))
        ):
            return True
        case _:
            return False


def parse_test_module(
    source: str, path_value: str, ctx: HookContext
) -> ast.Module | None:
    if not is_test_file(path_value):
        return None
    return parse_module(source, ctx.config.python_ast_max_parse_chars)


def iter_test_module_nodes(
    source: str, path_value: str, ctx: HookContext
) -> Iterator[ast.AST]:
    module = parse_test_module(source, path_value, ctx)
    if module is None:
        return
    yield from ast.walk(module)
