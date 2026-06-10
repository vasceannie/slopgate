"""Python AST runtime rules."""

from __future__ import annotations
import ast
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    pass
from slopgate.util.payloads import lower_path

BOUNDARY_LOG_METHODS = frozenset(
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
BOUNDARY_LOG_NAMES = frozenset(
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
EVENT_PATH_PARTS = frozenset(
    {"consumers", "events", "handlers", "listeners", "publishers", "subscribers"}
)
PACKAGE_BOUNDARY_PATH_PARTS = frozenset(
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
EVENT_CALL_NAMES = frozenset(
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
EVENT_NAME_MARKERS = frozenset(
    {"consume", "dispatch", "emit", "event", "handle", "notify", "publish", "subscribe"}
)
HTTP_BOUNDARY_METHODS = frozenset(
    {"delete", "execute", "get", "patch", "post", "put", "request", "send"}
)
PACKAGE_BOUNDARY_CLASS_SUFFIXES = (
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
PACKAGE_BOUNDARY_NAME_PARTS = frozenset(
    {"api", "client", "gateway", "http", "repository", "session", "transport"}
)


def path_parts(path_value: str) -> set[str]:
    normalized = path_value.replace("\\", "/").lower()
    return {part for part in normalized.split("/") if part}


def is_test_module_path(path_value: str) -> bool:
    normalized = lower_path(path_value)
    name = normalized.rsplit("/", 1)[-1]
    return (
        normalized.startswith("tests/")
        or "/tests/" in normalized
        or name.startswith("test_")
        or name.endswith("_test.py")
        or (name == "conftest.py")
    )


def attribute_chain_parts(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, ast.Attribute):
        return [*attribute_chain_parts(node.value), node.attr]
    if isinstance(node, ast.Call):
        return attribute_chain_parts(node.func)
    return []


def called_name(node: ast.Call) -> str:
    parts = attribute_chain_parts(node.func)
    return parts[-1] if parts else ""


def has_boundary_log_call(node: ast.AST) -> bool:
    for inner in ast.walk(node):
        if not isinstance(inner, ast.Call):
            continue
        func = inner.func
        if isinstance(func, ast.Name) and func.id.startswith(("log_", "record_metric")):
            return True
        if not isinstance(func, ast.Attribute):
            continue
        attr = func.attr
        parts = {part.lower().lstrip("_") for part in attribute_chain_parts(func.value)}
        if attr in BOUNDARY_LOG_METHODS and parts & BOUNDARY_LOG_NAMES:
            return True
        if attr.startswith(("log_", "record_metric")):
            return True
    return False


def function_name_has_event_signal(name: str) -> bool:
    parts = set(name.lower().split("_"))
    return bool(parts & EVENT_NAME_MARKERS) or name.lower().startswith("on_")


def contains_event_boundary_call(node: ast.AST) -> bool:
    for inner in ast.walk(node):
        if (
            isinstance(inner, ast.Call)
            and called_name(inner).lower() in EVENT_CALL_NAMES
        ):
            return True
    return False


def class_name_has_package_boundary_signal(class_name: str | None) -> bool:
    return bool(class_name and class_name.endswith(PACKAGE_BOUNDARY_CLASS_SUFFIXES))


def contains_package_boundary_call(node: ast.AST) -> bool:
    for inner in ast.walk(node):
        if not isinstance(inner, ast.Call):
            continue
        call_name = called_name(inner).lower()
        if call_name not in HTTP_BOUNDARY_METHODS:
            continue
        parts = {part.lower().lstrip("_") for part in attribute_chain_parts(inner.func)}
        if parts & PACKAGE_BOUNDARY_NAME_PARTS:
            return True
    return False


def boundary_kind_for_function(
    path_value: str,
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    class_name: str | None,
) -> str | None:
    parts = path_parts(path_value)
    if (
        parts & EVENT_PATH_PARTS
        or function_name_has_event_signal(node.name)
        or contains_event_boundary_call(node)
    ):
        return "event boundary"
    if (
        parts & PACKAGE_BOUNDARY_PATH_PARTS
        or class_name_has_package_boundary_signal(class_name)
        or contains_package_boundary_call(node)
    ):
        return "package boundary"
    return None


def iter_public_boundary_functions(
    body: list[ast.stmt], class_name: str | None = None
) -> list[tuple[ast.FunctionDef | ast.AsyncFunctionDef, str | None]]:
    functions: list[tuple[ast.FunctionDef | ast.AsyncFunctionDef, str | None]] = []
    for stmt in body:
        if isinstance(stmt, ast.ClassDef):
            functions.extend(iter_public_boundary_functions(stmt.body, stmt.name))
            continue
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if stmt.name.startswith("__") and stmt.name.endswith("__"):
                continue
            functions.append((stmt, class_name))
    return functions


class BoundaryFunction(NamedTuple):
    node: ast.FunctionDef | ast.AsyncFunctionDef
    kind: str
    class_name: str | None
