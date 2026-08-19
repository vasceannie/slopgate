"""Hypothesis references for incremental context helpers."""

from __future__ import annotations

from hypothesis import given, strategies

from slopgate.lint._collector_groups.incremental import (
    incremental_context,
    plan_with_index_dirty,
)
from slopgate.lint._collector_groups.incremental_cache import complete_incremental_results
from slopgate.lint._collector_groups.integrity_specs import lazy_integrity_index
from slopgate.lint._collector_groups.run_options import collector_options_from_env
from slopgate.lint._collector_groups.scheduling import parse_error_spec
from slopgate.lint._collector_groups.source_prepare import (
    build_analysis_index,
    last_parse_attempts,
)


@given(strategies.integers(min_value=0, max_value=2))
def test_incremental_context_helper_names(value: int) -> None:
    assert (
        incremental_context.__name__,
        plan_with_index_dirty.__name__,
        complete_incremental_results.__name__,
        lazy_integrity_index.__name__,
        collector_options_from_env.__name__,
        parse_error_spec.__name__,
        build_analysis_index.__name__,
        last_parse_attempts.__name__,
        value,
    )[-1] == value
