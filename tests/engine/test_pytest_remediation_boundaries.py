"""Regression coverage for the pytest smell remediation boundaries."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from slopgate._types import ObjectDict
from slopgate.engine import evaluate_payload
from tests.support import finding_ids

REMEDIATION_FIXTURES = Path(__file__).parent / "fixtures" / "pytest_remediation"
CASE_NAMES = ("loop", "parametrized", "bare", "messaged")


def test_pytest_remediation_boundaries_stay_stable_in_one_session(
    remediation_write: Callable[[str, str], ObjectDict],
) -> None:
    """Keep each remediation example independent while sharing one session."""
    result_ids = [
        finding_ids(
            evaluate_payload(
                remediation_write(
                    f"tests/test_{name}.py",
                    (REMEDIATION_FIXTURES / f"{name}.fixture").read_text(
                        encoding="utf-8"
                    ),
                )
            )
        )
        for name in CASE_NAMES
    ]
    loop_ids, parametrized_ids, bare_assert_ids, messaged_assert_ids = result_ids

    assert "PY-TEST-003" in loop_ids, "loop assertions should trigger PY-TEST-003"
    assert {"PY-TEST-001", "PY-TEST-003"}.isdisjoint(parametrized_ids), (
        f"parametrization should avoid test smell rules: {parametrized_ids}"
    )
    assert "PY-TEST-001" in bare_assert_ids, (
        "three adjacent bare assertions should trigger PY-TEST-001"
    )
    assert "PY-TEST-001" not in messaged_assert_ids, (
        "descriptive assertion messages should avoid PY-TEST-001"
    )
    all_ids = loop_ids | parametrized_ids | bare_assert_ids | messaged_assert_ids
    assert "RETRY-BUDGET-001" not in all_ids, (
        "independent remediation cases must not consume the retry budget"
    )
