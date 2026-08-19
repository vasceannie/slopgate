"""Parse-once source analysis helpers for collector runners."""

from __future__ import annotations

from contextvars import ContextVar
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING

from slopgate.lint._baseline import Violation
from slopgate.lint._collector_groups.types import SourceAnalysisOptions
from slopgate.lint._helpers import ParsedFile
from slopgate.lint._helpers.models import FileParseAttempt
from slopgate.lint._helpers.parsing import parse_file_attempts
from slopgate.lint.catalog import (
    OVERSIZED_MODULE_COLLECTORS,
    PROJECT_CONSTANT_SCAN_COLLECTORS,
)
from slopgate.lint.project_index import ProjectIndex, ProjectIndexRequest, build_project_index

if TYPE_CHECKING:
    from slopgate.quality.constant_index import ConstantIndex

_LAST_PARSE_ATTEMPTS: ContextVar[tuple[FileParseAttempt, ...] | None] = ContextVar(
    "slopgate_last_parse_attempts", default=None
)


def collect_parse_attempts(
    src_files: list[Path],
    test_files: list[Path],
    options: SourceAnalysisOptions,
) -> tuple[FileParseAttempt, ...]:
    """Parse source and test files once, recording the parse phase when profiled."""
    if options.attempts is not None:
        _LAST_PARSE_ATTEMPTS.set(options.attempts)
        return options.attempts
    started = perf_counter()
    targets = [*src_files, *test_files]
    if options.parse_paths is not None:
        targets = list(options.parse_paths)
    attempts = tuple(parse_file_attempts(targets))
    if options.profile is not None:
        options.profile.record_phase("parse", perf_counter() - started)
    _LAST_PARSE_ATTEMPTS.set(attempts)
    return attempts


def last_parse_attempts() -> tuple[FileParseAttempt, ...]:
    """Return parse attempts from the current source_analysis pass."""
    attempts = _LAST_PARSE_ATTEMPTS.get()
    return attempts if attempts is not None else ()


def parsed_groups(
    attempts: tuple[FileParseAttempt, ...], src_files: list[Path]
) -> tuple[list[ParsedFile], list[ParsedFile]]:
    """Split successful parses into source and test groups."""
    src_resolved = {path.resolve() for path in src_files}
    parsed_src = [
        attempt.parsed
        for attempt in attempts
        if attempt.parsed is not None and attempt.path.resolve() in src_resolved
    ]
    parsed_tests = [
        attempt.parsed
        for attempt in attempts
        if attempt.parsed is not None and attempt.path.resolve() not in src_resolved
    ]
    return parsed_src, parsed_tests


def maybe_oversized(
    parsed_src: list[ParsedFile],
    parsed_tests: list[ParsedFile],
    active_ids: frozenset[str] | None,
) -> list[Violation]:
    """Run oversized-module detection only when those collectors are active."""
    if active_ids is not None and active_ids.isdisjoint(OVERSIZED_MODULE_COLLECTORS):
        return []
    from slopgate.lint._detectors.code_smells import detect_oversized_modules

    return detect_oversized_modules([*parsed_src, *parsed_tests])


def maybe_literals(
    parsed_src: list[ParsedFile],
    project_root: Path,
    active_ids: frozenset[str] | None,
    build_constants: bool,
) -> list[Violation]:
    """Run repeated-literal detection, skipping the repo-wide constant walk when gated."""
    if active_ids is not None and active_ids.isdisjoint(PROJECT_CONSTANT_SCAN_COLLECTORS):
        return []
    from slopgate.lint._detectors.duplicates import detect_repeated_literals

    return detect_repeated_literals(
        parsed_src,
        constant_index=_session_constant_index(project_root, build_constants),
    )


def project_scope_hits(
    project_index: ProjectIndex,
    parsed_src: list[ParsedFile],
    options: SourceAnalysisOptions,
) -> list[Violation]:
    """Return project-scope duplicate hits from facts when present, else live ASTs."""
    from slopgate.lint._config import get_config

    if any(summary.facts.line_count for summary in project_index.files):
        return _hits_from_facts(project_index, options)
    root = get_config().project_root
    return [
        *maybe_literals(parsed_src, root, options.active_ids, options.build_constants),
        *_live_duplicate_hits(parsed_src),
    ]


def _hits_from_facts(
    project_index: ProjectIndex, options: SourceAnalysisOptions
) -> list[Violation]:
    from slopgate.lint._config import get_config
    from slopgate.lint.project_index.assemble import (
        block_violations,
        call_sequence_violations,
        clone_violations,
        literal_violations,
    )

    started = perf_counter()
    constant_index = _session_constant_index(
        get_config().project_root, options.build_constants, options
    )
    if options.profile is not None:
        options.profile.record_phase("constants", perf_counter() - started)
    return [
        *clone_violations(project_index),
        *block_violations(project_index),
        *call_sequence_violations(project_index),
        *literal_violations(project_index, constant_index),
    ]


def _session_constant_index(
    project_root: Path,
    build_constants: bool,
    options: SourceAnalysisOptions | None = None,
):
    from slopgate.quality.constant_index import (
        ConstantIndex,
        build_project_constant_index,
        get_session_constant_index,
        set_session_constant_index,
    )

    if not build_constants:
        constant_index = ConstantIndex(root=project_root, string_constants={}, files=())
        set_session_constant_index(constant_index)
        return constant_index
    existing = get_session_constant_index()
    if existing is not None and _constant_index_reusable(
        existing, project_root, options
    ):
        return existing
    dirty = () if options is None else (*options.dirty_paths, *options.deleted_paths)
    from slopgate.lint.project_index.constant_cache import (
        load_constant_index,
        save_constant_index,
    )

    cached = load_constant_index(project_root, dirty)
    if cached is not None:
        set_session_constant_index(cached)
        return cached
    constant_index = build_project_constant_index(project_root)
    if options is not None and options.persist_index:
        save_constant_index(project_root, constant_index)
    set_session_constant_index(constant_index)
    return constant_index


def _constant_index_reusable(
    existing: ConstantIndex,
    project_root: Path,
    options: SourceAnalysisOptions | None,
) -> bool:
    from slopgate.quality.constant_index import is_constant_candidate_path

    if existing.root != project_root.resolve():
        return False
    dirty = () if options is None else (*options.dirty_paths, *options.deleted_paths)
    invalidated = {path.resolve() for path in dirty}
    if any(path.resolve() in invalidated for path in existing.files):
        return False
    return not any(is_constant_candidate_path(path, project_root) for path in dirty)


def _live_duplicate_hits(parsed_src: list[ParsedFile]) -> list[Violation]:
    from slopgate.lint._detectors.duplicates import (
        detect_duplicate_call_sequences,
        detect_repeated_blocks,
        detect_semantic_clones,
    )

    return [
        *detect_semantic_clones(parsed_src),
        *detect_repeated_blocks(parsed_src),
        *detect_duplicate_call_sequences(parsed_src),
    ]


def build_analysis_index(
    src_files: list[Path],
    test_files: list[Path],
    options: SourceAnalysisOptions,
    project_root: Path,
) -> ProjectIndex:
    """Build the project index from retained parse attempts."""
    started = perf_counter()
    attempts = options.attempts or ()
    project_index = build_project_index(
        ProjectIndexRequest(
            root=project_root,
            src_files=tuple(src_files),
            test_files=tuple(test_files),
            dirty_paths=options.dirty_paths,
            attempts=attempts,
            persist=options.persist_index,
            use_store=options.use_index,
            rebuild=options.rebuild_index,
            fact_types=options.fact_types,
        )
    )
    if options.profile is not None:
        options.profile.record_phase("index-build", perf_counter() - started)
    return project_index
