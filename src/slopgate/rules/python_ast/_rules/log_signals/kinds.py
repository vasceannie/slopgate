"""Decide whether a function is an event or package boundary."""

from __future__ import annotations

import ast
from typing import NamedTuple

from . import classify
from .constants import (
    EVENT_PATH_PARTS,
    HTTP_BOUNDARY_METHODS,
    PACKAGE_BOUNDARY_CLASS_SUFFIXES,
    PACKAGE_BOUNDARY_NAME_PARTS,
    PACKAGE_BOUNDARY_PATH_PARTS,
)


class BoundaryFunction(NamedTuple):
    node: ast.FunctionDef | ast.AsyncFunctionDef
    kind: str
    class_name: str | None


def class_name_has_package_boundary_signal(class_name: str | None) -> bool:
    """Return True when class_name uses a package-boundary suffix."""
    if class_name is None:
        return False
    if class_name == "":
        return False
    return class_name.endswith(PACKAGE_BOUNDARY_CLASS_SUFFIXES)


def contains_package_boundary_call(node: ast.AST) -> bool:
    """Return True when node calls an HTTP/client-style helper."""
    for inner in ast.walk(node):
        if not isinstance(inner, ast.Call):
            continue
        call_name = classify.called_name(inner).lower()
        if call_name not in HTTP_BOUNDARY_METHODS:
            continue
        parts = {
            part.lower().lstrip("_")
            for part in classify.attribute_chain_parts(inner.func)
        }
        if parts & PACKAGE_BOUNDARY_NAME_PARTS:
            return True
    return False


def boundary_kind_for_function(
    path_value: str,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    class_name: str | None,
) -> str | None:
    """Return event/package kind when node is an observability boundary."""
    parts = classify.path_parts(path_value)
    if parts & EVENT_PATH_PARTS:
        return "event boundary"
    if classify.name_has_pubsub_marker(node.name):
        return "event boundary"
    if classify.contains_pubsub_call(node):
        return "event boundary"
    if parts & PACKAGE_BOUNDARY_PATH_PARTS:
        return "package boundary"
    if class_name_has_package_boundary_signal(class_name):
        return "package boundary"
    if contains_package_boundary_call(node):
        return "package boundary"
    return None


def iter_public_boundary_functions(
    body: list[ast.stmt], class_name: str | None = None
) -> list[tuple[ast.FunctionDef | ast.AsyncFunctionDef, str | None]]:
    """Collect public functions, pairing nested methods with their class."""
    functions: list[
        tuple[ast.FunctionDef | ast.AsyncFunctionDef, str | None]
    ] = []
    for stmt in body:
        if isinstance(stmt, ast.ClassDef):
            functions.extend(iter_public_boundary_functions(stmt.body, stmt.name))
            continue
        if not isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if stmt.name.startswith("__") and stmt.name.endswith("__"):
            continue
        functions.append((stmt, class_name))
    return functions
