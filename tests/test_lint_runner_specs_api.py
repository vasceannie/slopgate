"""Contract for CLI collector spec assembly."""

from __future__ import annotations

from slopgate.lint._collector_groups.runner_specs import (
    CollectorSpecInputs,
    cli_collector_specs,
)


def test_cli_collector_specs_include_parse_errors() -> None:
    inputs = CollectorSpecInputs(
        attempts=(),
        parsed_src=[],
        parsed_tests=[],
        file_local_src=[],
        file_local_tests=[],
        oversized=[],
        literals=[],
        integrity_mode="touched",
    )
    specs = cli_collector_specs(inputs)
    assert specs[0].collector_id == "python-parse-error"
