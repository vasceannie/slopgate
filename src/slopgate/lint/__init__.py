"""slopgate lint — batch code quality analysis with baseline tracking.

Absorbed from the standalone quality-gate tool.
"""
from __future__ import annotations

__version__ = "0.1.0"

from slopgate.lint._baseline import (
    BaselineResult,
    Violation,
    assert_no_new_violations,
    content_hash,
    load_baseline,
    save_baseline,
)
from slopgate.lint._config import QualityConfig, get_config, load_config, reset_config, set_config
from slopgate.lint._helpers import (
    find_all_python_files,
    find_source_files,
    find_test_files,
    relative_path,
    safe_parse,
)

__all__ = [
    "BaselineResult",
    "QualityConfig",
    "Violation",
    "assert_no_new_violations",
    "content_hash",
    "find_all_python_files",
    "find_source_files",
    "find_test_files",
    "get_config",
    "load_baseline",
    "load_config",
    "relative_path",
    "reset_config",
    "safe_parse",
    "save_baseline",
    "set_config",
]
