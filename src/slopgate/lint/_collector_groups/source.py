"""Source and touched-file collector groups."""

from __future__ import annotations

from pathlib import Path

from slopgate.lint._collector_groups.ast_collectors import ast_src_collectors
from slopgate.lint._collector_groups.pytest_file_collectors import test_collectors
from slopgate.lint._collector_groups.structure_collectors import structure_src_collectors
from slopgate.lint._collector_groups.types import SourceAnalysis, SourceAnalysisOptions


def source_analysis(
    src_files: list[Path],
    test_files: list[Path],
    options: SourceAnalysisOptions | None = None,
) -> SourceAnalysis:
    from dataclasses import replace

    from slopgate.lint._collector_groups.source_prepare import (
        build_analysis_index,
        collect_parse_attempts,
        maybe_oversized,
        parsed_groups,
        project_scope_hits,
    )
    from slopgate.lint._config import get_config

    controls = options or SourceAnalysisOptions()
    attempts = collect_parse_attempts(src_files, test_files, controls)
    controls = replace(controls, attempts=attempts)
    parsed_src, parsed_tests = parsed_groups(attempts, src_files)
    oversized = maybe_oversized(parsed_src, parsed_tests, controls.active_ids)
    project_root = get_config().project_root
    project_index = build_analysis_index(
        src_files, test_files, controls, project_root
    )
    literals = project_scope_hits(project_index, parsed_src, controls)
    return parsed_src, parsed_tests, oversized, literals, project_index


__all__ = [
    "ast_src_collectors",
    "source_analysis",
    "structure_src_collectors",
    "test_collectors",
]
