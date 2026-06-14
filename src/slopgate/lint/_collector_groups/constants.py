"""Collector routing constants."""

from __future__ import annotations

DEFERRED_TEST_INTEGRITY_COLLECTORS = frozenset(
    {
        "hypothesis-candidate",
        "missing-integration-test",
        "obsolete-or-deprecated-test",
        "untested-production-code",
    }
)
TOUCHED_TEST_INTEGRITY_COLLECTORS = frozenset(
    {
        "hand-built-test-payload",
        "mock-theater",
        "mocked-integration-test",
        "schema-bypass-test-data",
        "weak-test-assertion",
    }
)
OPT_IN_CLI_COLLECTORS = frozenset(
    {
        "dead-code",
        "boundary-logging",
        "feature-envy",
        "flat-sibling-files",
        "import-alias",
        "import-fanout",
        "langgraph-deprecated-api",
        "langgraph-state-mutation",
        "langgraph-state-reducer",
        "private-import-chain",
        "pytest-asyncio-pattern",
    }
)

__all__ = [
    "DEFERRED_TEST_INTEGRITY_COLLECTORS",
    "OPT_IN_CLI_COLLECTORS",
    "TOUCHED_TEST_INTEGRITY_COLLECTORS",
]
