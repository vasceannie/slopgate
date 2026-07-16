"""Privacy-safe feedback-loop evidence export."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from slopgate._types import ObjectDict, object_dict, object_list, string_value
from slopgate.constants import METADATA_PATH, UNKNOWN_VALUE

from ._load import default_log_path, load_entries

PY_LOG_002_RULE_ID: Final = "PY-LOG-002"
PY_LOG_002_RULE_PATH: Final = Path(
    "src/slopgate/rules/python_ast/_rules/_boundary_rule.py"
)
PY_LOG_002_RULE_SHA256: Final = (
    "f2f11cf43d91c5c26f0c3929e912fd3c0517fffc2ea93a45e1b3ba010a6c5fce"
)
CLASSIFICATION_CATEGORIES: Final = (
    "unclassified",
    "true_positive",
    "false_positive",
    "needs_context",
)
REVIEWER_STATUSES: Final = ("pending", "agreed", "disagreed")
PROHIBITED_FIELDS: Final = (
    "prompt",
    "patch",
    "tool_input",
    "updated_input",
    "updated_args",
    "proposed_content",
    "content",
    "source",
    "snippet",
    "code",
    "message",
    "additional_context",
    "output",
    "metadata",
)
ENFORCEMENT_DECISIONS: Final = frozenset({"deny", "block"})


@dataclass(frozen=True, slots=True)
class FeedbackEvidenceRequest:
    """Inputs for a deterministic PY-LOG-002 evidence export."""

    log_path: Path | None
    output_path: Path
    days: int | None
    sample_size: int


@dataclass(frozen=True, slots=True)
class FeedbackEvidenceSummary:
    """Counts emitted by a feedback evidence export."""

    available_denials: int
    sample_count: int
    output_path: Path


@dataclass(frozen=True, slots=True)
class InvalidSampleSizeError(ValueError):
    """Raised when an evidence request cannot select any records."""

    sample_size: int

    def __str__(self) -> str:
        return f"sample size must be positive, got {self.sample_size}"


@dataclass(frozen=True, slots=True)
class RuleAuditMismatchError(RuntimeError):
    """Raised when PY-LOG-002 changed after the evidence baseline was pinned."""

    expected: str
    actual: str

    def __str__(self) -> str:
        return (
            "PY-LOG-002 rule source changed: "
            f"expected {self.expected}, found {self.actual}"
        )


def _fingerprint(value: str) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode()).hexdigest()


def _rule_source_path() -> Path:
    return Path(__file__).parents[1] / "rules/python_ast/_rules/_boundary_rule.py"


def _audit_rule_source() -> str:
    digest = hashlib.sha256(_rule_source_path().read_bytes()).hexdigest()
    if digest != PY_LOG_002_RULE_SHA256:
        raise RuleAuditMismatchError(expected=PY_LOG_002_RULE_SHA256, actual=digest)
    return digest


def _safe_int(value: object, default: int) -> int:
    return value if isinstance(value, int) else default


def _safe_record(
    entry: ObjectDict,
    finding: ObjectDict,
    *,
    trace_location: tuple[int, int],
) -> ObjectDict:
    metadata = object_dict(finding.get("metadata"))
    path_value = string_value(metadata.get(METADATA_PATH)) or ""
    function_value = string_value(metadata.get("function")) or ""
    timestamp = string_value(entry.get("timestamp")) or ""
    record: ObjectDict = {
        "trace_locator": {
            "filtered_results_record": trace_location[0],
            "finding_index": trace_location[1],
        },
        "timestamp": timestamp,
        "event_name": string_value(entry.get("event_name")) or UNKNOWN_VALUE,
        "tool_name": string_value(entry.get("tool_name")) or UNKNOWN_VALUE,
        "platform": string_value(entry.get("platform")) or UNKNOWN_VALUE,
        "severity": string_value(finding.get("severity")) or UNKNOWN_VALUE,
        "decision": string_value(finding.get("decision")) or UNKNOWN_VALUE,
        "session_fingerprint": _fingerprint(
            string_value(entry.get("session_id")) or ""
        ),
        "path_fingerprint": _fingerprint(path_value),
        "path_suffix": Path(path_value).suffix if path_value else None,
        "function_fingerprint": _fingerprint(function_value),
        "boundary_kind": string_value(metadata.get("kind")) or UNKNOWN_VALUE,
        "line": _safe_int(metadata.get("line"), 0),
        "boundary_count": _safe_int(metadata.get("boundary_count"), 1),
        "classification": "unclassified",
        "reviewer_status": "pending",
    }
    record["record_id"] = hashlib.sha256(
        json.dumps(record, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return record


def _matching_records(entries: list[ObjectDict]) -> list[ObjectDict]:
    records: list[ObjectDict] = []
    for result_index, entry in enumerate(entries, start=1):
        for finding_index, raw_finding in enumerate(
            object_list(entry.get("findings")), start=1
        ):
            finding = object_dict(raw_finding)
            if finding.get("rule_id") != PY_LOG_002_RULE_ID:
                continue
            if finding.get("decision") not in ENFORCEMENT_DECISIONS:
                continue
            records.append(
                _safe_record(
                    entry,
                    finding,
                    trace_location=(result_index, finding_index),
                )
            )
    return records


def _artifact(
    records: list[ObjectDict], request: FeedbackEvidenceRequest, rule_sha256: str
) -> ObjectDict:
    selected = list(reversed(records[-request.sample_size :]))
    timestamps = [string_value(record.get("timestamp")) or "" for record in selected]
    return {
        "schema_version": 1,
        "rule_id": PY_LOG_002_RULE_ID,
        "rule_audit": {
            "rule_path": PY_LOG_002_RULE_PATH.as_posix(),
            "sha256": rule_sha256,
            "severity": "HIGH",
            "heuristics_changed": False,
        },
        "sample_policy": {
            "selection": "most_recent_first_from_append_order",
            "requested_records": request.sample_size,
            "days": request.days,
        },
        "available_denials": len(records),
        "sample_count": len(selected),
        "sample_window": {
            "newest": timestamps[0] if timestamps else None,
            "oldest": timestamps[-1] if timestamps else None,
        },
        "classification_categories": list(CLASSIFICATION_CATEGORIES),
        "reviewer_statuses": list(REVIEWER_STATUSES),
        "release_gate": {
            "status": "pending",
            "requirement": "independent_reviewer_agreement_post_deployment",
        },
        "prohibited_field_audit": {
            "status": "pass",
            "absent_record_keys": list(PROHIBITED_FIELDS),
        },
        "records": selected,
    }


def export_feedback_loop_evidence(
    request: FeedbackEvidenceRequest,
) -> FeedbackEvidenceSummary:
    """Export a redacted recent sample and enforce the unchanged-rule audit gate."""
    if request.sample_size <= 0:
        raise InvalidSampleSizeError(sample_size=request.sample_size)
    rule_sha256 = _audit_rule_source()
    log_path = request.log_path or default_log_path()
    records = _matching_records(load_entries(log_path, request.days))
    artifact = _artifact(records, request, rule_sha256)
    request.output_path.parent.mkdir(parents=True, exist_ok=True)
    _ = request.output_path.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return FeedbackEvidenceSummary(
        available_denials=len(records),
        sample_count=len(object_list(artifact.get("records"))),
        output_path=request.output_path,
    )
