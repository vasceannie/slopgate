"""LangGraph repository detectors."""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

from slopgate.constants import METADATA_PATH
from slopgate.lint._baseline import Violation
from slopgate.lint._config import get_config
from slopgate.lint._helpers import ParsedFile, ensure_parsed, find_source_files
from slopgate.rules.langgraph import (
    find_mutations,
    find_reducer_findings,
    is_langgraph_context,
    LangGraphStateReducerRule,
)

_OUTDATED_BUILDER_APIS = (
    (
        re.compile(r"\.set_entry_point\s*\("),
        "set_entry_point()",
        'add_edge(START, "node")',
    ),
    (
        re.compile(r"\.set_finish_point\s*\("),
        "set_finish_point()",
        'add_edge("node", END)',
    ),
)
_LANGGRAPH_BUILDER_API_COLLECTOR = "langgraph-deprecated-api"
_LANGGRAPH_BUILDER_API_TITLE = "Deprecated LangGraph API usage"


def _source(parsed_file: ParsedFile) -> str:
    return "\n".join(parsed_file.lines)


def _langgraph_files(
    files: Sequence[Path | ParsedFile] | None,
) -> list[tuple[ParsedFile, str]]:
    root = str(get_config().project_root)
    pairs: list[tuple[ParsedFile, str]] = []
    for parsed_file in ensure_parsed(files, fallback=find_source_files()):
        source = _source(parsed_file)
        if is_langgraph_context(source, root):
            pairs.append((parsed_file, source))
    return pairs


def detect_langgraph_state_reducers(
    files: Sequence[Path | ParsedFile] | None = None,
) -> list[Violation]:
    """Find LangGraph state list fields without reducers."""
    rule = LangGraphStateReducerRule()
    violations: list[Violation] = []
    for parsed_file, source in _langgraph_files(files):
        for finding in find_reducer_findings(parsed_file.rel, source, rule):
            class_name = str(finding.metadata.get("class", "state"))
            fields = finding.metadata.get("fields", [])
            violations.append(
                Violation(
                    rule="langgraph-state-reducer",
                    relative_path=parsed_file.rel,
                    identifier=class_name,
                    detail=f"fields={fields}",
                )
            )
    return violations


def detect_langgraph_state_mutations(
    files: Sequence[Path | ParsedFile] | None = None,
) -> list[Violation]:
    """Find likely direct state mutation in LangGraph source files."""
    violations: list[Violation] = []
    for parsed_file, source in _langgraph_files(files):
        mutations = find_mutations(source)
        if not mutations:
            continue
        line_no, preview = mutations[0]
        violations.append(
            Violation(
                rule="langgraph-state-mutation",
                relative_path=parsed_file.rel,
                identifier=f"line-{line_no}",
                detail=f"mutations={len(mutations)} first={preview}",
            )
        )
    return violations


def detect_langgraph_builder_api(
    files: Sequence[Path | ParsedFile] | None = None,
) -> list[Violation]:
    """Find outdated LangGraph builder API calls."""
    violations: list[Violation] = []
    for parsed_file, source in _langgraph_files(files):
        for pattern, old_api, new_api in _OUTDATED_BUILDER_APIS:
            if not pattern.search(source):
                continue
            violations.append(
                Violation(
                    rule=_LANGGRAPH_BUILDER_API_COLLECTOR,
                    relative_path=parsed_file.rel,
                    identifier=old_api,
                    detail=f"{old_api}->{new_api}",
                    metadata={
                        METADATA_PATH: parsed_file.rel,
                        "title": _LANGGRAPH_BUILDER_API_TITLE,
                    },
                )
            )
    return violations
