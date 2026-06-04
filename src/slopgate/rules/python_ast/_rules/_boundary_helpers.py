"""Python AST runtime rules."""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING, NamedTuple
if TYPE_CHECKING:
    pass

from slopgate.util.payloads import lower_path as lower_path


_BOUNDARY_LOG_METHODS = frozenset(
    {
        "bind",
        "critical",
        "debug",
        "error",
        "exception",
        "info",
        "log",
        "notice",
        "warning",
        "warn",
    }
)
_BOUNDARY_LOG_NAMES = frozenset(
    {
        "audit",
        "audit_logger",
        "event_logger",
        "logger",
        "log",
        "metrics",
        "observability",
        "telemetry",
        "tracer",
    }
)
_EVENT_PATH_PARTS = frozenset(
    {
        "consumers",
        "events",
        "handlers",
        "listeners",
        "publishers",
        "subscribers",
    }
)
_PACKAGE_BOUNDARY_PATH_PARTS = frozenset(
    {
        "adapters",
        "api",
        "boundaries",
        "boundary",
        "clients",
        "gateways",
        "integrations",
        "ports",
        "repositories",
        "transport",
        "transports",
    }
)
_EVENT_CALL_NAMES = frozenset(
    {
        "broadcast",
        "consume",
        "dispatch",
        "emit",
        "enqueue_event",
        "fire_event",
        "handle_event",
        "notify",
        "publish",
        "publish_event",
        "record_event",
        "send_event",
        "subscribe",
        "trigger_event",
    }
)
_EVENT_NAME_MARKERS = frozenset(
    {
        "consume",
        "dispatch",
        "emit",
        "event",
        "handle",
        "notify",
        "publish",
        "subscribe",
    }
)
_HTTP_BOUNDARY_METHODS = frozenset(
    {"delete", "execute", "get", "patch", "post", "put", "request", "send"}
)
_PACKAGE_BOUNDARY_CLASS_SUFFIXES = (
    "Adapter",
    "Api",
    "API",
    "Client",
    "Gateway",
    "Integration",
    "Port",
    "Repository",
    "Transport",
)
_PACKAGE_BOUNDARY_NAME_PARTS = frozenset(
    {
        "api",
        "client",
        "gateway",
        "http",
        "repository",
        "session",
        "transport",
    }
)


def _path_parts(path_value: str) -> set[str]:
    normalized = path_value.replace("\\", "/").lower()
    return {part for part in normalized.split("/") if part}


def _is_test_module_path(path_value: str) -> bool:
    normalized = lower_path(path_value)
    name = normalized.rsplit("/", 1)[-1]
    return (
        normalized.startswith("tests/")
        or "/tests/" in normalized
        or name.startswith("test_")
        or name.endswith("_test.py")
        or name == "conftest.py"
    )


def _attribute_chain_parts(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Attribute):
        return [*_attribute_chain_parts(node.value), node.attr]
    if isinstance(node, ast.Call):
        return _attribute_chain_parts(node.func)
    return []


def _called_name(node: ast.Call) -> str:
    parts = _attribute_chain_parts(node.func)
    return parts[-1] if parts else ""


def _has_boundary_log_call(node: ast.AST) -> bool:
    for inner in ast.walk(node):
        if not isinstance(inner, ast.Call):
            continue
        func = inner.func
        if isinstance(func, ast.Name) and func.id.startswith(("log_", "record_metric")):
            return True
        if not isinstance(func, ast.Attribute):
            continue
        attr = func.attr
        parts = {part.lower().lstrip("_") for part in _attribute_chain_parts(func.value)}
        if attr in _BOUNDARY_LOG_METHODS and parts & _BOUNDARY_LOG_NAMES:
            return True
        if attr.startswith(("log_", "record_metric")):
            return True
    return False


def _function_name_has_event_signal(name: str) -> bool:
    parts = set(name.lower().split("_"))
    return bool(parts & _EVENT_NAME_MARKERS) or name.lower().startswith("on_")


def _contains_event_boundary_call(node: ast.AST) -> bool:
    for inner in ast.walk(node):
        if isinstance(inner, ast.Call) and _called_name(inner).lower() in _EVENT_CALL_NAMES:
            return True
    return False


def _class_name_has_package_boundary_signal(class_name: str | None) -> bool:
    return bool(class_name and class_name.endswith(_PACKAGE_BOUNDARY_CLASS_SUFFIXES))


def _contains_package_boundary_call(node: ast.AST) -> bool:
    for inner in ast.walk(node):
        if not isinstance(inner, ast.Call):
            continue
        call_name = _called_name(inner).lower()
        if call_name not in _HTTP_BOUNDARY_METHODS:
            continue
        parts = {part.lower().lstrip("_") for part in _attribute_chain_parts(inner.func)}
        if parts & _PACKAGE_BOUNDARY_NAME_PARTS:
            return True
    return False


def _boundary_kind_for_function(
    path_value: str,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    class_name: str | None,
) -> str | None:
    parts = _path_parts(path_value)
    if (
        parts & _EVENT_PATH_PARTS
        or _function_name_has_event_signal(node.name)
        or _contains_event_boundary_call(node)
    ):
        return "event boundary"
    if (
        parts & _PACKAGE_BOUNDARY_PATH_PARTS
        or _class_name_has_package_boundary_signal(class_name)
        or _contains_package_boundary_call(node)
    ):
        return "package boundary"
    return None


def _iter_public_boundary_functions(
    body: list[ast.stmt],
    class_name: str | None = None,
) -> list[tuple[ast.FunctionDef | ast.AsyncFunctionDef, str | None]]:
    functions: list[tuple[ast.FunctionDef | ast.AsyncFunctionDef, str | None]] = []
    for stmt in body:
        if isinstance(stmt, ast.ClassDef):
            functions.extend(_iter_public_boundary_functions(stmt.body, stmt.name))
            continue
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if stmt.name.startswith("__") and stmt.name.endswith("__"):
                continue
            functions.append((stmt, class_name))
    return functions


class _BoundaryFunction(NamedTuple):
    node: ast.FunctionDef | ast.AsyncFunctionDef
    kind: str
    class_name: str | None
