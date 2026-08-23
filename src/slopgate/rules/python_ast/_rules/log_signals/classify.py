"""AST helpers that detect observability-worthy call sites."""

from __future__ import annotations

import ast

from slopgate.util.payloads import lower_path

from .constants import (
    BOUNDARY_LOG_METHODS,
    BOUNDARY_LOG_NAMES,
    EVENT_CALL_NAMES,
    EVENT_NAME_MARKERS,
)


def path_parts(path_value: str) -> set[str]:
    """Return lowercased path segments for classifier lookups."""
    normalized = path_value.replace("\\", "/").lower()
    return {part for part in normalized.split("/") if part}


def is_test_module_path(path_value: str) -> bool:
    """Return True when path_value looks like a test module."""
    normalized = lower_path(path_value)
    name = normalized.rsplit("/", 1)[-1]
    if normalized.startswith("tests/"):
        return True
    if "/tests/" in normalized:
        return True
    if name.startswith("test_"):
        return True
    if name.endswith("_test.py"):
        return True
    return name == "conftest.py"


def attribute_chain_parts(node: ast.AST) -> list[str]:
    """Return attribute names along a Name/Attribute/Call chain."""
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Attribute):
        return [*attribute_chain_parts(node.value), node.attr]
    if isinstance(node, ast.Call):
        return attribute_chain_parts(node.func)
    return []


def called_name(node: ast.Call) -> str:
    """Return the last attribute or name used as a call target."""
    parts = attribute_chain_parts(node.func)
    if not parts:
        return ""
    return parts[-1]


def _call_has_logger(inner: ast.Call) -> bool:
    """Return True when inner is a project logger or metric call."""
    func = inner.func
    if isinstance(func, ast.Name):
        return func.id in BOUNDARY_LOG_NAMES or func.id.startswith(
            ("log_", "record_metric")
        )
    if not isinstance(func, ast.Attribute):
        return False
    attr = func.attr
    parts = {part.lower().lstrip("_") for part in attribute_chain_parts(func.value)}
    if attr in BOUNDARY_LOG_METHODS and parts & BOUNDARY_LOG_NAMES:
        return True
    return attr.startswith(("log_", "record_metric"))


def has_boundary_log_call(node: ast.AST) -> bool:
    """Return True when node contains a logger or metric call."""
    for inner in ast.walk(node):
        if isinstance(inner, ast.Call) and _call_has_logger(inner):
            return True
    return False


def name_has_pubsub_marker(name: str) -> bool:
    """Return True when a function name looks like a pub/sub handler."""
    parts = set(name.lower().split("_"))
    if parts & EVENT_NAME_MARKERS:
        return True
    return name.lower().startswith("on_")


def contains_pubsub_call(node: ast.AST) -> bool:
    """Return True when node calls a publish/subscribe helper."""
    for inner in ast.walk(node):
        if not isinstance(inner, ast.Call):
            continue
        if called_name(inner).lower() in EVENT_CALL_NAMES:
            return True
    return False


function_name_has_event_signal = name_has_pubsub_marker
contains_event_boundary_call = contains_pubsub_call
