from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Literal, TypeAlias, TypedDict

from .coercion import (
    coerce_dict_list,
    coerce_object_dict,
    coerce_object_list,
    coerce_str_list,
)

Category: TypeAlias = Literal["events", "rules", "results", "subprocesses"]
JSONDict: TypeAlias = dict[str, object]


class SlopgateConfig(TypedDict):
    enabled_rules: dict[str, bool]
    enabled_cli_rules: dict[str, bool]
    rule_surfaces: JSONDict
    rule_counterparts: dict[str, list[str]]
    regex_rules: list[JSONDict]
    skip_paths: list[str]


JSONL_FILES = [
    "events.jsonl",
    "rules.jsonl",
    "results.jsonl",
    "subprocess.jsonl",
    "async/subprocess.jsonl",
]
DEFAULT_REMOTE_LOGS = "~/.config/slopgate/logs"
DEFAULT_LOOKBACK_HOURS = 24
TOOL_INPUT_TEXT_LIMIT = 20000
MAX_RECORDS_PER_CATEGORY: dict[Category, int] = {
    "events": 6000,
    "rules": 6000,
    "results": 6000,
    "subprocesses": 2000,
}
TRACE_META_KEYS = (
    "platform_capability",
    "degraded_reason",
    "enforcement_mode",
    "resolved_repo_root",
    "session_title",
    "session_title_source",
    "session_identity_source",
    "opencode_session_id",
    "codex_session_id",
    "secondary_session_ids",
    "parent_session_id",
    "root_session_id",
    "origin_platform",
    "origin_session_id",
    "platform_source",
    "subagent_type",
    "spawn_description",
    "lineage_role",
)
TRACE_META_ALIASES: dict[str, tuple[str, ...]] = {
    "session_title": (
        "session_title",
        "sessionTitle",
        "thread_title",
        "threadTitle",
        "conversation_title",
        "conversationTitle",
    ),
    "session_title_source": ("session_title_source", "sessionTitleSource"),
    "session_identity_source": ("session_identity_source", "sessionIdentitySource"),
    "opencode_session_id": (
        "opencode_session_id",
        "opencodeSessionId",
        "opencodeSessionID",
    ),
    "codex_session_id": (
        "codex_session_id",
        "codexSessionId",
        "codexSessionID",
        "thread_id",
        "threadId",
        "threadID",
        "conversation_id",
        "conversationId",
        "conversationID",
    ),
    "secondary_session_ids": ("secondary_session_ids", "secondarySessionIds"),
    "parent_session_id": ("parent_session_id", "parentSessionId", "parentSessionID"),
    "root_session_id": ("root_session_id", "rootSessionId", "rootSessionID"),
    "origin_platform": ("origin_platform", "originPlatform"),
    "origin_session_id": ("origin_session_id", "originSessionId", "originSessionID"),
    "platform_source": ("platform_source", "platformSource"),
    "subagent_type": ("subagent_type", "subagentType"),
    "spawn_description": ("spawn_description", "spawnDescription"),
    "lineage_role": ("lineage_role", "lineageRole"),
}
KNOWN_PLATFORMS = {"claude", "codex", "opencode", "cursor", "unknown"}
KNOWN_PLATFORM_SOURCES = {"explicit", "defaulted", "normalized", "unknown"}
METADATA_VALUE_OMITTED = object()
DASHBOARD_DIR = Path(__file__).resolve().parent.parent.parent
DIST_DIR = DASHBOARD_DIR / "dist"
CANVAS_DEPLOY = Path.home() / ".openclaw" / "canvas" / "forcedash"


def classify(obj: Mapping[str, object]) -> Category | None:
    """Classify a parsed JSONL line into a trace category."""
    if "command" in obj and "returncode" in obj:
        return "subprocesses"
    if "findings" in obj and isinstance(obj.get("findings"), list):
        return "results"
    if "rule_id" in obj:
        return "rules"
    if "event_name" in obj and "session_id" in obj:
        return "events"
    return None


def _trim_text(value: object, limit: int) -> str | None:
    """Return a bounded string payload for dashboard display."""
    if not isinstance(value, str):
        return None
    if len(value) <= limit:
        return value
    return value[:limit] + "…[trimmed]"


def _trace_metadata(
    obj: Mapping[str, object], *, include_bare_title: bool = False
) -> JSONDict:
    """Preserve small, non-payload trace context already emitted by the engine."""
    meta: JSONDict = {}
    for key in TRACE_META_KEYS:
        aliases = TRACE_META_ALIASES.get(key, (key,))
        if key == "session_title" and include_bare_title:
            aliases = (*aliases, "title")
        for source_key in aliases:
            if source_key not in obj:
                continue
            value = _trace_metadata_value(key, obj[source_key])
            if value is not METADATA_VALUE_OMITTED:
                meta[key] = value
            break
    meta.setdefault("platform_source", _platform_source(obj))
    return meta


def _trace_metadata_value(key: str, value: object) -> object:
    if key == "secondary_session_ids":
        return _trace_string_list_value(value)
    if key == "origin_platform":
        return _trace_platform_value(value)
    if key == "platform_source":
        return _trace_platform_source_value(value)
    return value if isinstance(value, str) or value is None else METADATA_VALUE_OMITTED


def _trace_string_list_value(value: object) -> object:
    if value is None:
        return None
    if isinstance(value, str):
        return [value] if value.strip() else METADATA_VALUE_OMITTED
    string_values = coerce_str_list(value)
    return string_values if string_values else METADATA_VALUE_OMITTED


def _trace_platform_value(value: object) -> object:
    return _platform_value(value) if isinstance(value, str) else _nullable_value(value)


def _trace_platform_source_value(value: object) -> object:
    if isinstance(value, str) and value in KNOWN_PLATFORM_SOURCES:
        return value
    return _nullable_value(value)


def _nullable_value(value: object) -> object:
    return None if value is None else METADATA_VALUE_OMITTED


def _platform_value(value: object) -> str:
    return value if isinstance(value, str) and value in KNOWN_PLATFORMS else "unknown"


def _platform_source(obj: Mapping[str, object]) -> str:
    value = obj.get("platform_source") or obj.get("platformSource")
    if isinstance(value, str) and value in KNOWN_PLATFORM_SOURCES:
        return value
    raw_platform = obj.get("platform")
    if raw_platform is None or raw_platform == "":
        return "unknown"
    return "explicit" if _platform_value(raw_platform) != "unknown" else "normalized"


def _format_tool_input(value: object) -> JSONDict | None:
    """Preserve bounded tool arguments needed for dashboard drill-downs."""
    source = coerce_object_dict(value)
    if source is None:
        return None
    projected: JSONDict = {}
    for key, item in source.items():
        if isinstance(item, str):
            projected[key] = _trim_text(item, TOOL_INPUT_TEXT_LIMIT) or ""
        elif isinstance(item, (bool, int, float)) or item is None:
            projected[key] = item
    return projected


def _format_e(obj: Mapping[str, object]) -> JSONDict:
    return {
        "timestamp": obj.get("timestamp", ""),
        "platform": _platform_value(obj.get("platform")),
        "event_name": obj.get("event_name", ""),
        "session_id": obj.get("session_id", ""),
        "tool_name": obj.get("tool_name", ""),
        "candidate_paths": coerce_str_list(obj.get("candidate_paths")),
        "languages": coerce_str_list(obj.get("languages")),
        "model": obj.get("model"),
        "provider": obj.get("provider"),
        "command": _trim_text(obj.get("command"), 1000),
        "tool_output": _trim_text(obj.get("tool_output"), 1000),
        "tool_input": _format_tool_input(obj.get("tool_input")),
        **_trace_metadata(obj, include_bare_title=True),
    }


def _format_ru(obj: Mapping[str, object]) -> JSONDict:
    return {
        "timestamp": obj.get("timestamp", ""),
        "platform": _platform_value(obj.get("platform")),
        "event_name": obj.get("event_name", ""),
        "session_id": obj.get("session_id", ""),
        "tool_name": obj.get("tool_name", ""),
        "rule_id": obj.get("rule_id", ""),
        "severity": obj.get("severity", "LOW"),
        "decision": obj.get("decision"),
        "message": _trim_text(obj.get("message"), 180),
        "additional_context": _trim_text(obj.get("additional_context"), 180),
        "metadata": {},
        "model": obj.get("model"),
        "provider": obj.get("provider"),
        "command": _trim_text(obj.get("command"), 1000),
        "tool_output": _trim_text(obj.get("tool_output"), 1000),
        "tool_input": _format_tool_input(obj.get("tool_input")),
        **_trace_metadata(obj),
    }


def _format_res(obj: Mapping[str, object]) -> JSONDict:
    findings: list[JSONDict] = []
    for finding_value in coerce_dict_list(obj.get("findings")):
        finding = coerce_object_dict(finding_value)
        if finding is not None:
            findings.append(
                {
                    "rule_id": finding.get("rule_id", ""),
                    "severity": finding.get("severity", "LOW"),
                    "decision": finding.get("decision"),
                    "message": _trim_text(finding.get("message"), 180),
                    "additional_context": _trim_text(
                        finding.get("additional_context"), 180
                    ),
                    **_trace_metadata(finding),
                }
            )
    return {
        "timestamp": obj.get("timestamp", ""),
        "platform": _platform_value(obj.get("platform")),
        "event_name": obj.get("event_name", ""),
        "session_id": obj.get("session_id", ""),
        "tool_name": obj.get("tool_name", ""),
        "findings": findings,
        "errors": [
            text
            for err in coerce_object_list(obj.get("errors"))
            for text in [_trim_text(err, 180)]
            if text is not None
        ],
        "output": None,
        "skipped": bool(obj.get("skipped", False)),
        "reason": _trim_text(obj.get("reason"), 180),
        "model": obj.get("model"),
        "provider": obj.get("provider"),
        "command": _trim_text(obj.get("command"), 1000),
        "tool_output": _trim_text(obj.get("tool_output"), 1000),
        "tool_input": _format_tool_input(obj.get("tool_input")),
        **_trace_metadata(obj),
    }


def _format_sub(obj: Mapping[str, object]) -> JSONDict:
    return {
        "timestamp": obj.get("timestamp", ""),
        "event_name": obj.get("event_name", ""),
        "session_id": obj.get("session_id", ""),
        "command": _trim_text(obj.get("command"), 180) or "",
        "cwd": _trim_text(obj.get("cwd"), 120) or "",
        "returncode": obj.get("returncode", 0),
        "stdout": _trim_text(obj.get("stdout"), 120) or "",
        "stderr": _trim_text(obj.get("stderr"), 180) or "",
        "duration_ms": obj.get("duration_ms", 0),
    }


def format_item(obj: Mapping[str, object]) -> JSONDict | None:
    """Keep only the fields ForceDash actually reads."""
    category = classify(obj)
    if category == "events":
        return _format_e(obj)
    if category == "rules":
        return _format_ru(obj)
    if category == "results":
        return _format_res(obj)
    if category == "subprocesses":
        return _format_sub(obj)
    return None
