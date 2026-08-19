"""Logger and observability name sets for boundary classification."""

from __future__ import annotations

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
    {
        "consumers",
        "events",
        "handlers",
        "listeners",
        "publishers",
        "subscribers",
    }
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
HTTP_BOUNDARY_METHODS = frozenset(
    {
        "delete",
        "execute",
        "get",
        "patch",
        "post",
        "put",
        "request",
        "send",
    }
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
