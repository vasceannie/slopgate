"""Stats regressions for legacy regex metadata path resolution."""

from __future__ import annotations

from typing import Final

from slopgate._types import ObjectDict, object_dict
from slopgate.constants import METADATA_DECISION
from slopgate.stats import analyze
from tests.support import nested_output, pair_counts

LEGACY_HITS_ENTRY: Final[ObjectDict] = {
    "timestamp": "2026-04-01T12:00:00+00:00",
    "event_name": "PreToolUse",
    "session_id": "s1",
    "tool_name": "Write",
    "findings": [
        {
            "rule_id": "PY-QUALITY-010",
            METADATA_DECISION: "deny",
            "severity": "HIGH",
            "message": "Magic number",
            "metadata": {"target": "content", "hits": ["src/app.py"]},
        }
    ],
}


def test_legacy_hits_only_metadata_counts_denied_file() -> None:
    stats = object_dict(analyze([LEGACY_HITS_ENTRY, LEGACY_HITS_ENTRY]))

    assert pair_counts(stats, "top_files_denied").get("src/app.py") == 2, (
        "hits-only metadata should still count the denied file"
    )


def test_legacy_hits_only_metadata_counts_looping_file() -> None:
    stats = object_dict(analyze([LEGACY_HITS_ENTRY, LEGACY_HITS_ENTRY]))
    legacy = nested_output(nested_output(stats, "legacy_metrics"), "legacy_churn")

    assert pair_counts(legacy, "top_looping_files").get("file:target-1") == 2, (
        "hits-only metadata should route repeated denies to one redacted file target"
    )


def test_legacy_hits_only_metadata_is_not_pathless() -> None:
    stats = object_dict(analyze([LEGACY_HITS_ENTRY, LEGACY_HITS_ENTRY]))
    legacy = nested_output(nested_output(stats, "legacy_metrics"), "legacy_churn")

    assert "PY-QUALITY-010" not in pair_counts(legacy, "top_pathless_loop_rules"), (
        "file-backed hits-only metadata should not count as pathless"
    )
