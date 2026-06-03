"""Detector for stale / deprecated code patterns.

Flags lines matching configurable regex patterns (e.g. old-style typing
imports that should use modern ``X | Y`` syntax).
"""
from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path

from vibeforcer.lint._baseline import Violation
from vibeforcer.lint._config import get_config
from vibeforcer.lint._helpers import ParsedFile, ensure_parsed, find_source_files


def detect_deprecated_patterns(
    files: Sequence[Path | ParsedFile] | None = None,
) -> list[Violation]:
    """Scan source files for lines matching deprecated-pattern regexes."""
    cfg = get_config()
    if not cfg.deprecated_patterns:
        return []

    compiled: list[tuple[re.Pattern[str], str]] = []
    for pattern_str, description in cfg.deprecated_patterns:
        try:
            compiled.append((re.compile(pattern_str), description))
        except re.error:
            continue

    parsed = ensure_parsed(files, fallback=find_source_files())
    violations: list[Violation] = []

    for pf in parsed:
        for lineno, line in enumerate(pf.lines, 1):
            stripped = line.strip()
            # Skip comments
            if stripped.startswith("#"):
                continue
            for regex, desc in compiled:
                if regex.search(line):
                    violations.append(
                        Violation(
                            rule="deprecated-pattern",
                            relative_path=pf.rel,
                            identifier=f"L{lineno}",
                            detail=desc,
                        )
                    )
                    break  # one violation per line

    return violations
