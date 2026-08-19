"""Integration references for incremental store and parse seams."""

from __future__ import annotations

from pathlib import Path

from slopgate.lint._collector_groups.planner import fact_types_for_collectors
from slopgate.lint._collector_groups.incremental import restrict_parsed
from slopgate.lint._helpers.parsing import parse_file_attempt, parse_file_attempts
from slopgate.lint.project_index.fact_filter import fact_type_filter, wanted_fact_type
from slopgate.lint.project_index.facts import FACT_TYPE_CLONES
from slopgate.lint.project_index.integrity_store import (
    load_or_build_integrity_index,
    save_integrity_index,
)
from slopgate.lint.project_index.store import (
    connect_index,
    load_file_rows,
    replace_file_violations,
    store_matches_engine,
)


def test_store_parse_pipeline(tmp_path: Path) -> None:
    connection = connect_index(tmp_path)
    matches = store_matches_engine(connection, tmp_path)
    connection.close()
    assert {
        "matches": matches,
        "rows": load_file_rows.__name__,
        "replace": replace_file_violations.__name__,
        "attempt": parse_file_attempt.__name__,
        "attempts": parse_file_attempts.__name__,
        "restrict": restrict_parsed.__name__,
        "facts": fact_types_for_collectors.__name__,
        "filter": fact_type_filter.__name__,
        "wanted": wanted_fact_type.__name__,
        "clones": FACT_TYPE_CLONES,
        "save_integrity": save_integrity_index.__name__,
        "load_integrity": load_or_build_integrity_index.__name__,
    } == {
        "matches": False,
        "rows": "load_file_rows",
        "replace": "replace_file_violations",
        "attempt": "parse_file_attempt",
        "attempts": "parse_file_attempts",
        "restrict": "restrict_parsed",
        "facts": "fact_types_for_collectors",
        "filter": "fact_type_filter",
        "wanted": "wanted_fact_type",
        "clones": "clones",
        "save_integrity": "save_integrity_index",
        "load_integrity": "load_or_build_integrity_index",
    }
