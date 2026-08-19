"""AST source collector specs."""

from __future__ import annotations

from slopgate.lint._collector_groups.scheduling import CollectorSpec, execute_all
from slopgate.lint._collector_groups.types import CollectorResults
from slopgate.lint._helpers import ParsedFile


def ast_src_collector_specs(parsed_src: list[ParsedFile]) -> list[CollectorSpec]:
    """Return deferred AST-based source collectors."""
    from slopgate.lint._detectors.exception_safety import (
        detect_broad_except_swallow,
        detect_silent_except,
        detect_silent_fallback,
    )
    from slopgate.lint._detectors.langgraph import (
        detect_langgraph_builder_api,
        detect_langgraph_state_mutations,
        detect_langgraph_state_reducers,
    )
    from slopgate.lint._detectors.line_length import detect_long_lines
    from slopgate.lint._detectors.logging_conventions import (
        detect_boundary_logging,
        detect_direct_get_logger,
        detect_wrong_logger_name,
    )
    from slopgate.lint._detectors.stale_code import detect_stale_patterns
    from slopgate.lint._detectors.type_safety import (
        detect_any_usage,
        detect_type_suppressions,
    )
    from slopgate.lint._detectors.wrappers import detect_unnecessary_wrappers

    return [
        CollectorSpec("unnecessary-wrapper", lambda: detect_unnecessary_wrappers(parsed_src)),
        CollectorSpec("deprecated-pattern", lambda: detect_stale_patterns(parsed_src)),
        CollectorSpec("langgraph-deprecated-api", lambda: detect_langgraph_builder_api(parsed_src)),
        CollectorSpec("langgraph-state-mutation", lambda: detect_langgraph_state_mutations(parsed_src)),
        CollectorSpec("langgraph-state-reducer", lambda: detect_langgraph_state_reducers(parsed_src)),
        CollectorSpec("boundary-logging", lambda: detect_boundary_logging(parsed_src)),
        CollectorSpec("direct-get-logger", lambda: detect_direct_get_logger(parsed_src)),
        CollectorSpec("wrong-logger-name", lambda: detect_wrong_logger_name(parsed_src)),
        CollectorSpec("banned-any", lambda: detect_any_usage(parsed_src)),
        CollectorSpec("type-suppression", lambda: detect_type_suppressions(parsed_src)),
        CollectorSpec("broad-except-swallow", lambda: detect_broad_except_swallow(parsed_src)),
        CollectorSpec("silent-datetime-fallback", lambda: detect_silent_fallback(parsed_src)),
        CollectorSpec("silent-except", lambda: detect_silent_except(parsed_src)),
        CollectorSpec("long-line", lambda: detect_long_lines(parsed_src)),
    ]


def ast_src_collectors(parsed_src: list[ParsedFile]) -> CollectorResults:
    """Collect AST-based source violations (type safety, exceptions, logging)."""
    return execute_all(ast_src_collector_specs(parsed_src))
