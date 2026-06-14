"""Collector registry facade.

The collector implementation lives in ``slopgate.lint._collector_groups`` so
this legacy module can remain a stable import surface for CLI, hooks, and tests.
"""

from __future__ import annotations

from slopgate.lint._collector_groups.constants import (
    DEFERRED_TEST_INTEGRITY_COLLECTORS,
    OPT_IN_CLI_COLLECTORS,
    TOUCHED_TEST_INTEGRITY_COLLECTORS,
)
from slopgate.lint._collector_groups.integrity import full_integrity_collectors
from slopgate.lint._collector_groups.runners import (
    run_all_collectors,
    run_test_integrity_collectors,
    run_touched_collectors,
)
from slopgate.lint._collector_groups.source import (
    ast_src_collectors,
    source_analysis,
    structure_src_collectors,
    test_collectors,
)
from slopgate.lint._collector_groups.types import CollectorResults, SourceAnalysis

test_integrity_collectors = full_integrity_collectors

__all__ = [
    "CollectorResults",
    "DEFERRED_TEST_INTEGRITY_COLLECTORS",
    "OPT_IN_CLI_COLLECTORS",
    "SourceAnalysis",
    "TOUCHED_TEST_INTEGRITY_COLLECTORS",
    "ast_src_collectors",
    "run_all_collectors",
    "run_test_integrity_collectors",
    "run_touched_collectors",
    "source_analysis",
    "structure_src_collectors",
    "test_collectors",
    "test_integrity_collectors",
]
