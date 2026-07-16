"""Privacy and audit contracts for feedback-loop evidence exports."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from slopgate._types import object_dict, object_list
from slopgate.cli.cli import build_parser
from slopgate.stats import (
    FeedbackEvidenceRequest,
    FeedbackEvidenceSummary,
    export_feedback_loop_evidence,
)
from slopgate.stats import evidence
from slopgate.stats.evidence import InvalidSampleSizeError, RuleAuditMismatchError

RULE_SOURCE = Path("src/slopgate/rules/python_ast/_rules/_boundary_rule.py")
PINNED_RULE_SHA256 = "f2f11cf43d91c5c26f0c3929e912fd3c0517fffc2ea93a45e1b3ba010a6c5fce"
SECRET_TEXT = "private prompt and proposed source content"
SAMPLE_SIZE = 100
PROHIBITED_RECORD_KEYS = {
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
}


def _result_entry(index: int) -> dict[str, object]:
    timestamp = datetime(2026, 7, 1, tzinfo=UTC) + timedelta(minutes=index)
    return {
        "timestamp": timestamp.isoformat(),
        "event_name": "PreToolUse",
        "session_id": f"session-{index}",
        "tool_name": "Write",
        "platform": "claude",
        "prompt": SECRET_TEXT,
        "tool_input": {"content": SECRET_TEXT, "patch": SECRET_TEXT},
        "output": {"reason": SECRET_TEXT},
        "findings": [
            {
                "rule_id": "PY-LOG-002",
                "decision": "deny" if index % 2 == 0 else "block",
                "severity": "HIGH",
                "message": SECRET_TEXT,
                "additional_context": SECRET_TEXT,
                "metadata": {
                    "path": f"/private/project/src/module_{index}.py",
                    "function": f"handler_{index}",
                    "kind": "event boundary",
                    "line": index + 1,
                    "source": SECRET_TEXT,
                    "snippet": SECRET_TEXT,
                },
            }
        ],
    }


def _write_results(path: Path, count: int) -> None:
    entries = (_result_entry(index) for index in range(count))
    path.write_text(
        "".join(f"{json.dumps(entry)}\n" for entry in entries),
        encoding="utf-8",
    )


def _nested_keys(value: object) -> set[str]:
    mapping = object_dict(value)
    keys = set(mapping)
    for nested_value in mapping.values():
        keys.update(_nested_keys(nested_value))
    for nested_value in object_list(value):
        keys.update(_nested_keys(nested_value))
    return keys


def test_feedback_evidence_export_is_deterministic(
    tmp_path: Path,
) -> None:
    source = tmp_path / "results.jsonl"
    first_output = tmp_path / "first.json"
    second_output = tmp_path / "second.json"
    _write_results(source, SAMPLE_SIZE + 5)
    export_feedback_loop_evidence(
        FeedbackEvidenceRequest(source, first_output, None, SAMPLE_SIZE)
    )
    export_feedback_loop_evidence(
        FeedbackEvidenceRequest(source, second_output, None, SAMPLE_SIZE)
    )

    assert first_output.read_bytes() == second_output.read_bytes(), (
        "identical inputs should produce byte-identical evidence"
    )


def test_feedback_evidence_export_is_privacy_safe(tmp_path: Path) -> None:
    source = tmp_path / "results.jsonl"
    output = tmp_path / "evidence.json"
    _write_results(source, SAMPLE_SIZE + 5)

    summary = export_feedback_loop_evidence(
        FeedbackEvidenceRequest(source, output, None, SAMPLE_SIZE)
    )

    artifact = json.loads(output.read_text(encoding="utf-8"))
    serialized = output.read_text(encoding="utf-8")
    assert isinstance(summary, FeedbackEvidenceSummary), (
        "Evidence exports should return the public summary value"
    )
    assert summary.sample_count == SAMPLE_SIZE, "export should contain 100 records"
    assert artifact["available_denials"] == SAMPLE_SIZE + 5, (
        "artifact should report all matching denials"
    )
    assert SECRET_TEXT not in serialized, "prohibited source content must be absent"
    assert "/private/project" not in serialized, "raw source paths must be hashed"
    assert not (PROHIBITED_RECORD_KEYS & _nested_keys(artifact["records"])), (
        "exported records must omit prohibited fields recursively"
    )


def test_feedback_evidence_export_represents_review_workflow(tmp_path: Path) -> None:
    source = tmp_path / "results.jsonl"
    output = tmp_path / "evidence.json"
    _write_results(source, 1)

    export_feedback_loop_evidence(
        FeedbackEvidenceRequest(source, output, None, SAMPLE_SIZE)
    )

    artifact = json.loads(output.read_text(encoding="utf-8"))
    record = artifact["records"][0]
    assert artifact["classification_categories"] == [
        "unclassified",
        "true_positive",
        "false_positive",
        "needs_context",
    ], "artifact should enumerate classification outcomes"
    assert artifact["reviewer_statuses"] == [
        "pending",
        "agreed",
        "disagreed",
    ], "artifact should enumerate reviewer states"
    assert record["classification"] == "unclassified", (
        "new evidence should await classification"
    )
    assert record["reviewer_status"] == "pending", (
        "independent review should remain pending before deployment"
    )
    assert artifact["release_gate"]["status"] == "pending", (
        "release gate should remain pending until independent review"
    )


def test_feedback_evidence_export_rejects_non_positive_sample_size(
    tmp_path: Path,
) -> None:
    source = tmp_path / "results.jsonl"
    _write_results(source, 1)

    with pytest.raises(InvalidSampleSizeError):
        export_feedback_loop_evidence(
            FeedbackEvidenceRequest(source, tmp_path / "evidence.json", None, 0)
        )


def test_feedback_evidence_export_rejects_rule_audit_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "results.jsonl"
    _write_results(source, 1)
    monkeypatch.setattr(evidence, "PY_LOG_002_RULE_SHA256", "mismatch")

    with pytest.raises(RuleAuditMismatchError):
        export_feedback_loop_evidence(
            FeedbackEvidenceRequest(
                source, tmp_path / "evidence.json", None, SAMPLE_SIZE
            )
        )


def test_stats_parser_supports_feedback_evidence_export() -> None:
    parsed = build_parser().parse_args(
        [
            "stats",
            "--days",
            "42",
            "--export-evidence",
            "docs/evidence/sample.json",
            "--sample-size",
            "100",
        ]
    )

    assert (
        parsed.command,
        parsed.days,
        parsed.export_evidence,
        parsed.sample_size,
    ) == (
        "stats",
        42,
        "docs/evidence/sample.json",
        100,
    ), "stats parser should expose the supported evidence workflow"


def test_py_log_002_rule_source_matches_preimplementation_audit_hash() -> None:
    digest = hashlib.sha256(RULE_SOURCE.read_bytes()).hexdigest()

    assert digest == PINNED_RULE_SHA256, (
        "PY-LOG-002 rule code changed; independent audit is required before export"
    )
