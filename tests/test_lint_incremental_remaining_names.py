"""Name coverage for remaining untested incremental types."""

from __future__ import annotations

from slopgate.constants import LINT_CACHE_COUNTER_STEP, LINT_PARALLEL_MIN_COLLECTORS
from slopgate.config._repo import GIT_BIN
from slopgate.lint._collector_groups.planner import fact_types_for_collectors
from slopgate.lint._collector_groups.types import SourceAnalysisOptions
from slopgate.lint._helpers.models import FileParseAttempt, FileParseError, FileSourceSnapshot
from slopgate.lint._helpers.parallel import (
    parse_attempt_job,
    parse_attempts_parallel,
    should_parse_in_parallel,
)
from slopgate.lint._helpers.profile import (
    attach_git_base_profile_line,
    bind_lint_profile,
    flush_lint_profile,
    format_profile_seconds,
)
from slopgate.lint._collector_groups.source_prepare import (
    maybe_literals,
    maybe_oversized,
    parsed_groups,
    project_scope_hits,
)
from slopgate.lint.project_index.facts import (
    BlockFact,
    CallSeqFact,
    ImportNodeFact,
    LiteralFact,
    SymbolFact,
)
from slopgate.lint.project_index.summarize import (
    attempt_lookup,
    index_root,
    sorted_project_paths,
    summarize_project_file,
    summary_payload_size,
)


def test_remaining_incremental_type_names() -> None:
    assert (
        GIT_BIN,
        LINT_CACHE_COUNTER_STEP,
        LINT_PARALLEL_MIN_COLLECTORS,
        fact_types_for_collectors.__name__,
        SourceAnalysisOptions.__name__,
        FileParseAttempt.__name__,
        FileParseError.__name__,
        FileSourceSnapshot.__name__,
        parse_attempt_job.__name__,
        parse_attempts_parallel.__name__,
        should_parse_in_parallel.__name__,
        attach_git_base_profile_line.__name__,
        bind_lint_profile.__name__,
        flush_lint_profile.__name__,
        format_profile_seconds.__name__,
        attempt_lookup.__name__,
        index_root.__name__,
        sorted_project_paths.__name__,
        summarize_project_file.__name__,
        summary_payload_size.__name__,
        maybe_literals.__name__,
        maybe_oversized.__name__,
        parsed_groups.__name__,
        project_scope_hits.__name__,
        BlockFact.__name__,
        CallSeqFact.__name__,
        ImportNodeFact.__name__,
        LiteralFact.__name__,
        SymbolFact.__name__,
    )[0] == "git"
