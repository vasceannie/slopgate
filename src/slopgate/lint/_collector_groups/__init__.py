"""Internal collector implementation groups."""

from slopgate.lint._collector_groups.source import (
    ast_src_collectors,
    source_analysis,
    structure_src_collectors,
    test_collectors,
)

__all__ = [
    "ast_src_collectors",
    "source_analysis",
    "structure_src_collectors",
    "test_collectors",
]
