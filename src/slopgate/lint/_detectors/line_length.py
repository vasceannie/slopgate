"""Detector for over-long lines.

``detect_long_lines`` — find lines exceeding the configured max length,
skipping string literals (docstrings), comments, URLs, import statements, and
whitespace-only padding. Trailing whitespace does not count toward the code
line length.

Uses AST-derived string-literal line ranges instead of fragile triple-quote
counting.
"""

from __future__ import annotations

import re
from pathlib import Path

from slopgate.lint._baseline import Violation
from slopgate.lint._config import get_config
from slopgate.lint._helpers import ParsedFile, ensure_parsed, find_source_files

_URL_RE = re.compile(r"https?://")


def detect_long_lines(
    files: list[Path] | list[ParsedFile] | None = None,
) -> list[Violation]:
    """Find lines exceeding ``cfg.max_line_length``.

    Skips:
    - Lines inside string literals (docstrings, triple-quoted strings)
    - Whitespace-only lines and trailing whitespace padding
    - Comment-only lines
    - Lines containing URLs (``http://`` or ``https://``)
    - Import statements (``import …`` / ``from … import …``)
    """
    cfg = get_config()
    max_len = cfg.max_line_length
    parsed = ensure_parsed(files, fallback=find_source_files())
    violations: list[Violation] = []

    for pf in parsed:
        for lineno, line in enumerate(pf.lines, start=1):
            # Skip lines inside string literals (AST-derived)
            if lineno in pf.string_line_ranges:
                continue

            stripped = line.strip()
            if not stripped:
                continue

            # Skip comment-only lines
            if stripped.startswith("#"):
                continue

            # Skip import statements
            if stripped.startswith("import ") or stripped.startswith("from "):
                continue

            # Skip lines containing URLs
            if _URL_RE.search(line):
                continue

            # Check executable code length. Formatting-only trailing spaces are
            # whitespace debt, not a reason to tell agents to mangle code/docs.
            line_len = len(line.rstrip())
            if line_len > max_len:
                violations.append(
                    Violation(
                        rule="long-line",
                        relative_path=pf.rel,
                        identifier=f"line-{lineno}",
                        detail=f"length={line_len}",
                    )
                )

    return violations
