"""AST utility helpers for lint detectors."""

from __future__ import annotations

import ast


def _span_lines(nodes: list[ast.stmt]) -> int:
    if not nodes:
        return 0
    start = nodes[0].lineno
    end_node = nodes[-1]
    end = getattr(end_node, "end_lineno", end_node.lineno)
    return end - start + 1


def without_leading_docstring(nodes: list[ast.stmt]) -> list[ast.stmt]:
    if not nodes:
        return []
    first = nodes[0]
    if (
        isinstance(first, ast.Expr)
        and isinstance(first.value, ast.Constant)
        and isinstance(first.value.value, str)
    ):
        return nodes[1:]
    return nodes


def function_body_lines(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    """Count the lines in a function body (excluding decorators and docstrings)."""
    return _span_lines(without_leading_docstring(node.body))


def class_body_lines(node: ast.ClassDef) -> int:
    """Count the total lines spanned by a class body."""
    return _span_lines(node.body)


def count_methods(node: ast.ClassDef) -> int:
    """Count the number of method definitions in a class (direct children only)."""
    return sum(
        1
        for child in node.body
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
    )


def build_parent_map(tree: ast.Module) -> dict[int, ast.AST]:
    """Build a mapping from ``id(child)`` to parent node."""
    parents: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[id(child)] = node
    return parents


def compute_string_line_ranges(tree: ast.Module) -> set[int]:
    """Return the line numbers occupied by string constants in the AST."""
    string_lines: set[int] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and hasattr(node, "lineno")
            and hasattr(node, "end_lineno")
        ):
            end_line = node.end_lineno if node.end_lineno is not None else node.lineno
            for line_number in range(node.lineno, end_line + 1):
                string_lines.add(line_number)
    return string_lines


def enclosing_function(
    node: ast.AST,
    parent_map: dict[int, ast.AST],
) -> str:
    """Walk up the parent map to find the enclosing function name."""
    current: ast.AST | None = parent_map.get(id(node))
    while current is not None:
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current.name
        current = parent_map.get(id(current))
    return "<module>"
