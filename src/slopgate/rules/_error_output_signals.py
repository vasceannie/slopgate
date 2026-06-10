"""Detect actionable error signals in Bash command output."""

from __future__ import annotations

import re

_ERROR_PATTERNS = [
    re.compile(r"\bFAILED\b.*test", re.IGNORECASE),
    re.compile(r"\bFAIL\s+(?:src/|tests/)", re.IGNORECASE),
    re.compile(r"Tests?:\s+\d+\s+failed", re.IGNORECASE),
    re.compile(r"test result: FAILED", re.IGNORECASE),
    re.compile(r"\d+\s+failed,\s+\d+\s+passed", re.IGNORECASE),
    re.compile(r"^.*:\d+:\d+:\s+error:", re.MULTILINE),
    re.compile(r"make:\s+\*\*\*.*Error\s+\d+", re.IGNORECASE),
    re.compile(r"Build FAILED", re.IGNORECASE),
    re.compile(r"compilation\s+error", re.IGNORECASE),
    re.compile(r"Traceback \(most recent call last\)"),
    re.compile(
        r"(?:SyntaxError|TypeError|NameError|ValueError|AttributeError"
        + r"|ImportError|KeyError|IndexError|RuntimeError|AssertionError"
        + r"|FileNotFoundError|ModuleNotFoundError|OSError|PermissionError):",
        re.MULTILINE,
    ),
    re.compile(r"Found\s+\d+\s+error", re.IGNORECASE),
    re.compile(r"error\[E\d+\]", re.IGNORECASE),
    re.compile(r"✗|✘"),
]

_FALSE_POSITIVE_PATTERNS = [
    re.compile(r"^\s*\d+\s+passed(?:\s+in\s+[\d.]+s)?\s*$", re.MULTILINE),
    re.compile(
        r"DEPRECATION:|DeprecationWarning|PendingDeprecationWarning", re.IGNORECASE
    ),
    re.compile(r"\d+\s+warnings?\s+found\s+\(use\s+docker", re.IGNORECASE),
    re.compile(r"Successfully\s+(built|installed|tagged|created)", re.IGNORECASE),
]


def has_error_signals(output: str) -> bool:
    """Check if command output contains real error signals."""
    if not output or len(output.strip()) < 10:
        return False

    has_success = any(p.search(output) for p in _FALSE_POSITIVE_PATTERNS)
    error_hits = sum(1 for p in _ERROR_PATTERNS if p.search(output))

    if error_hits == 0:
        return False

    if has_success and error_hits <= 1:
        return False

    return True
