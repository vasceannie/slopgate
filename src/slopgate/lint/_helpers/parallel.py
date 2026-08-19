"""Parallel parse-once for large lint inventories."""

from __future__ import annotations

import os
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from slopgate.constants import LINT_PARALLEL_MIN_FILES
from slopgate.lint._helpers.models import FileParseAttempt


def should_parse_in_parallel(paths: Sequence[Path]) -> bool:
    """Return True when process-pool parsing is worth the spawn cost."""
    return len(paths) >= LINT_PARALLEL_MIN_FILES


def parse_attempt_job(path: Path) -> FileParseAttempt:
    """Picklable worker that parses one path in a child process."""
    from slopgate.lint._helpers.parsing import parse_file_attempt

    return parse_file_attempt(path)


def parse_attempts_parallel(paths: Sequence[Path]) -> list[FileParseAttempt]:
    """Parse *paths* with a process pool, preserving input order."""
    workers = os.cpu_count()
    max_workers = workers if workers is not None and workers > 1 else 1
    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        return list(pool.map(parse_attempt_job, paths))
