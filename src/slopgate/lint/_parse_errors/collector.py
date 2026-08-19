"""Python parse-error lint collector backed by the request-local parse cache."""

from __future__ import annotations

from pathlib import Path

from slopgate.lint._baseline import Violation
from slopgate.lint._collector_groups.scheduling import parse_error_violations
from slopgate.lint._helpers.parsing import parse_file_attempts


def detect_python_parse_errors(paths: list[Path]) -> list[Violation]:
    """Return baseline-able violations for Python files that cannot be parsed."""
    if not paths:
        return []
    return parse_error_violations(parse_file_attempts(paths))
