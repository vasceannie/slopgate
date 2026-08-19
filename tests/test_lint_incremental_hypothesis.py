"""Hypothesis references for incremental parse helpers."""

from __future__ import annotations

from hypothesis import given, strategies

from slopgate.lint._collector_groups.source_prepare import collect_parse_attempts
from slopgate.lint._helpers.parsing import parse_file_attempt, parse_file_attempts
from slopgate.lint._collector_groups.incremental import restrict_parsed
from slopgate.lint._collector_groups.planner import build_lint_plan, fact_types_for_collectors
from slopgate.lint._parse_errors import detect_python_parse_errors
from slopgate.lint.project_index.facts import FACT_TYPE_CLONES


@given(strategies.integers(min_value=0, max_value=2))
def test_parse_helper_names(value: int) -> None:
    assert (
        collect_parse_attempts.__name__,
        parse_file_attempt.__name__,
        parse_file_attempts.__name__,
        restrict_parsed.__name__,
        build_lint_plan.__name__,
        fact_types_for_collectors.__name__,
        FACT_TYPE_CLONES,
        detect_python_parse_errors.__name__,
        value,
    )[-1] == value
