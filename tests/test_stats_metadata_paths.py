"""Stats regressions for legacy regex metadata path resolution."""

from __future__ import annotations

from slopgate._types import ObjectDict, object_dict, object_list
from slopgate.stats import analyze


def pair_counts(stats: ObjectDict, key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in object_list(stats.get(key)):
        pair = object_list(item)
        if len(pair) != 2:
            continue
        name, count = pair
        if isinstance(name, str) and isinstance(count, int):
            counts[name] = count
    return counts


def test_legacy_hits_only_metadata_counts_as_file_backed_churn() -> None:
    entry: ObjectDict = {
        "timestamp": "2026-04-01T12:00:00+00:00",
        "event_name": "PreToolUse",
        "session_id": "s1",
        "tool_name": "Write",
        "findings": [
            {
                "rule_id": "PY-QUALITY-010",
                "decision": "deny",
                "severity": "HIGH",
                "message": "Magic number",
                "metadata": {"target": "content", "hits": ["src/app.py"]},
            }
        ],
    }
    stats = object_dict(analyze([entry, entry]))

    assert pair_counts(stats, "top_files_denied").get("src/app.py") == 2, (
        "hits-only metadata should still count the denied file"
    )
    assert pair_counts(stats, "top_looping_files").get("src/app.py") == 2, (
        "hits-only metadata should route repeated denies to the real file"
    )
    assert "PY-QUALITY-010" not in pair_counts(stats, "top_pathless_loop_rules"), (
        "file-backed hits-only metadata should not count as pathless"
    )
