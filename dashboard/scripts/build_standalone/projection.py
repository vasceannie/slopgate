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
)
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


def _trace_metadata(obj: Mapping[str, object]) -> JSONDict:
    """Preserve small, non-payload trace context already emitted by the engine."""
    meta: JSONDict = {}
    for key in TRACE_META_KEYS:
        if key in obj:
            value = obj[key]
            if isinstance(value, str) or value is None:
                meta[key] = value
    return meta


def _format_e(obj: Mapping[str, object]) -> JSONDict:
    return {
        "timestamp": obj.get("timestamp", ""),
        "platform": obj.get("platform", "claude"),
        "event_name": obj.get("event_name", ""),
        "session_id": obj.get("session_id", ""),
        "tool_name": obj.get("tool_name", ""),
        "candidate_paths": coerce_str_list(obj.get("candidate_paths")),
        "languages": coerce_str_list(obj.get("languages")),
        "model": obj.get("model"),
        "provider": obj.get("provider"),
        "command": _trim_text(obj.get("command"), 1000),
        "tool_output": _trim_text(obj.get("tool_output"), 1000),
        **_trace_metadata(obj),
    }


def _format_ru(obj: Mapping[str, object]) -> JSONDict:
    return {
        "timestamp": obj.get("timestamp", ""),
        "platform": obj.get("platform", "claude"),
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
        "platform": obj.get("platform", "claude"),
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
