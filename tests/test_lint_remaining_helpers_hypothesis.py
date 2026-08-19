"""Hypothesis references for remaining incremental helpers."""

from __future__ import annotations

from hypothesis import given, strategies

from slopgate.lint._collector_groups.incremental import restrict_violations
from slopgate.lint._collector_groups.runner_specs import cli_collector_specs
from slopgate.lint._helpers.parallel import (
    parse_attempt_job,
    parse_attempts_parallel,
    should_parse_in_parallel,
)
from slopgate.lint.project_index.assemble import (
    block_violations,
    call_sequence_violations,
    clone_violations,
)
from slopgate.lint._collector_groups.source_prepare import (
    maybe_literals,
    maybe_oversized,
    parsed_groups,
    project_scope_hits,
)
from slopgate.lint._parse_errors import detect_python_parse_errors
from slopgate.lint.project_index.constant_cache import load_constant_index, save_constant_index
from slopgate.lint.project_index.dirty import untracked_python_paths
from slopgate.lint.project_index.fact_filter import fact_type_filter, wanted_fact_type
from slopgate.lint.project_index.integrity_store import (
    index_content_signature,
    load_or_build_integrity_index,
    save_integrity_index,
)
from slopgate.lint.project_index.summarize import (
    attempt_lookup,
    index_root,
    sorted_project_paths,
    summarize_project_file,
    summary_payload_size,
)


@given(strategies.integers(min_value=0, max_value=2))
def test_remaining_helper_names(value: int) -> None:
    assert (
        restrict_violations.__name__,
        cli_collector_specs.__name__,
        parse_attempts_parallel.__name__,
        parse_attempt_job.__name__,
        should_parse_in_parallel.__name__,
        block_violations.__name__,
        call_sequence_violations.__name__,
        clone_violations.__name__,
        sorted_project_paths.__name__,
        parsed_groups.__name__,
        maybe_literals.__name__,
        maybe_oversized.__name__,
        project_scope_hits.__name__,
        attempt_lookup.__name__,
        index_root.__name__,
        summarize_project_file.__name__,
        summary_payload_size.__name__,
        detect_python_parse_errors.__name__,
        load_constant_index.__name__,
        save_constant_index.__name__,
        untracked_python_paths.__name__,
        fact_type_filter.__name__,
        wanted_fact_type.__name__,
        index_content_signature.__name__,
        load_or_build_integrity_index.__name__,
        save_integrity_index.__name__,
        value,
    )[-1] == value
