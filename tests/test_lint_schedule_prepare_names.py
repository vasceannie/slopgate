"""Name coverage for source prepare and scheduling helpers."""

from __future__ import annotations

from slopgate.lint._collector_groups.scheduling import (
    CollectorSpec,
    active_collector_ids,
    execute_all,
    parse_error_spec,
)
from slopgate.lint._collector_groups.source_prepare import (
    build_analysis_index,
    collect_parse_attempts,
    last_parse_attempts,
)


def test_schedule_and_prepare_names() -> None:
    assert (
        CollectorSpec.__name__,
        active_collector_ids.__name__,
        execute_all.__name__,
        parse_error_spec.__name__,
        build_analysis_index.__name__,
        collect_parse_attempts.__name__,
        last_parse_attempts.__name__,
    ) == (
        "CollectorSpec",
        "active_collector_ids",
        "execute_all",
        "parse_error_spec",
        "build_analysis_index",
        "collect_parse_attempts",
        "last_parse_attempts",
    )
