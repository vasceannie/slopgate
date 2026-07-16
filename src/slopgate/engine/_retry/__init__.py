"""Compatibility facade for retry policy and diagnostics."""

from __future__ import annotations

from .budget import (
    capture_repair_plan_signal,
    enforce_retry_budget,
    record_full_read_evidence,
)
from .common import dedupe_findings, filter_search_reminder_dedupe
from .guidance import RecoveryGuidance, recovery_guidance
from .identity import (
    attempt_fingerprint,
    normalize_attempt_path,
    operation_category,
    semantic_enforcement_key,
)
from .steering import apply_loop_aware_steering, inject_recent_failure_context

__all__ = [
    "RecoveryGuidance",
    "apply_loop_aware_steering",
    "attempt_fingerprint",
    "capture_repair_plan_signal",
    "dedupe_findings",
    "enforce_retry_budget",
    "filter_search_reminder_dedupe",
    "inject_recent_failure_context",
    "normalize_attempt_path",
    "operation_category",
    "record_full_read_evidence",
    "recovery_guidance",
    "semantic_enforcement_key",
]
