"""Assemble deferred collector specs for CLI and hook runners."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from slopgate.lint._collector_groups.ast_collectors import ast_src_collector_specs
from slopgate.lint._collector_groups.integrity import full_integrity_collector_specs
from slopgate.lint._collector_groups.integrity_specs import (
    touched_integrity_collector_specs,
)
from slopgate.lint._collector_groups.pytest_file_collectors import test_collector_specs
from slopgate.lint._collector_groups.run_options import IntegrityMode
from slopgate.lint._collector_groups.scheduling import CollectorSpec, parse_error_spec
from slopgate.lint._collector_groups.structure_collectors import (
    structure_src_collector_specs,
)
from slopgate.lint._helpers import ParsedFile
from slopgate.lint._helpers.models import FileParseAttempt
from slopgate.lint._baseline import Violation
from slopgate.lint.project_index import ProjectIndex


@dataclass(frozen=True, slots=True)
class CollectorSpecInputs:
    """Parsed files and precomputed hits used to build deferred collector specs."""

    attempts: tuple[FileParseAttempt, ...]
    parsed_src: list[ParsedFile]
    parsed_tests: list[ParsedFile]
    file_local_src: list[ParsedFile]
    file_local_tests: list[ParsedFile]
    oversized: list[Violation]
    literals: list[Violation]
    integrity_mode: IntegrityMode
    project_index: ProjectIndex | None = None


def cli_collector_specs(inputs: CollectorSpecInputs) -> list[CollectorSpec]:
    """Return CLI collector specs including suite integrity."""
    specs = [
        parse_error_spec(inputs.attempts),
        *structure_src_collector_specs(
            inputs.parsed_src,
            inputs.oversized,
            inputs.literals,
            inputs.file_local_src,
        ),
        *ast_src_collector_specs(inputs.file_local_src),
        *test_collector_specs(inputs.file_local_tests),
        *_regex_specs(inputs.file_local_src, inputs.file_local_tests),
    ]
    integrity_specs: dict[IntegrityMode, Callable[[], list[CollectorSpec]]] = {
        "full": lambda: full_integrity_collector_specs(
            inputs.parsed_src,
            inputs.parsed_tests,
            None,
            inputs.project_index,
        ),
        "touched": lambda: touched_integrity_collector_specs(inputs.file_local_tests),
    }
    specs.extend(integrity_specs[inputs.integrity_mode]())
    return specs


def _regex_specs(
    parsed_src: list[ParsedFile], parsed_tests: list[ParsedFile]
) -> list[CollectorSpec]:
    from slopgate.lint._regex_rules import (
        cli_regex_rule_configs,
        regex_rule_collectors,
    )

    holder: list[dict[str, list[Violation]] | None] = [None]

    def hits_for(rule_id: str) -> list[Violation]:
        if holder[0] is None:
            holder[0] = dict(regex_rule_collectors(parsed_src, parsed_tests))
        return holder[0].get(rule_id, [])

    return [
        CollectorSpec(config.rule_id, lambda rid=config.rule_id: hits_for(rid))
        for config in cli_regex_rule_configs()
    ]
