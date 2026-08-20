"""Enforcement-mode isolation for improvement metrics."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from slopgate._types import object_dict, object_list
from slopgate.stats import build_improvement


def _first_attempt_clean_rate(mode: str) -> dict[str, object]:
    fixture_path = (
        Path(__file__).parent
        / "fixtures"
        / "improvement"
        / "mixed_enforcement_first_attempt_clean.json"
    )
    fixture = object_dict(json.loads(fixture_path.read_text(encoding="utf-8")))
    payload = build_improvement(object_list(fixture.get("entries")))
    by_mode = object_dict(payload.get("by_enforcement_mode"))
    metrics = object_dict(by_mode.get(mode))
    return object_dict(metrics.get("first_attempt_clean_rate"))


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("repo_strict", {"rate": 0.0, "numerator": 0, "denominator": 1}),
        ("repo_relaxed", {"rate": 1.0, "numerator": 1, "denominator": 1}),
    ],
    ids=["strict-excludes-relaxed", "relaxed-excludes-strict"],
)
def test_first_attempt_clean_is_scoped_by_enforcement_mode(
    mode: str, expected: dict[str, object]
) -> None:
    assert _first_attempt_clean_rate(mode) == expected, (
        f"first-attempt-clean for {mode} must exclude other enforcement modes"
    )
