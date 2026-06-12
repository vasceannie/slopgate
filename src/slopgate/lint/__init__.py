"""slopgate lint — batch code quality analysis with baseline tracking.

Absorbed from the standalone quality-gate tool.
"""

from __future__ import annotations

from slopgate import __version__

__all__ = [
    "BaselineResult",
    "BaselineSyncResult",
    "apply_lint_baseline_sync",
    "compute_synced_baseline_rules",
    "QualityConfig",
    "Violation",
    "assert_no_new_violations",
    "content_hash",
    "find_all_python_files",
    "find_source_files",
    "find_test_files",
    "get_config",
    "ensure_parsed",
    "load_baseline",
    "load_config",
    "parse_file",
    "parse_files",
    "ParsedFile",
    "relative_path",
    "reset_config",
    "safe_parse",
    "save_baseline",
    "save_baseline_ids",
    "set_config",
    "__version__",
]

from slopgate.lint._baseline import (
    BaselineResult,
    BaselineSyncResult,
    Violation,
    apply_lint_baseline_sync,
    compute_synced_baseline_rules,
    assert_no_new_violations,
    content_hash,
    load_baseline,
    save_baseline,
    save_baseline_ids,
)
from slopgate.lint._config import (
    QualityConfig,
    get_config,
    load_config,
    reset_config,
    set_config,
)
from slopgate.lint._helpers import (
    ParsedFile,
    ensure_parsed,
    find_all_python_files,
    find_source_files,
    find_test_files,
    parse_file,
    parse_files,
    relative_path,
    safe_parse,
)

__all__ = [
    "BaselineResult",
    "BaselineSyncResult",
    "apply_lint_baseline_sync",
    "compute_synced_baseline_rules",
    "QualityConfig",
    "Violation",
    "assert_no_new_violations",
    "content_hash",
    "find_all_python_files",
    "find_source_files",
    "find_test_files",
    "get_config",
    "ensure_parsed",
    "load_baseline",
    "load_config",
    "parse_file",
    "parse_files",
    "ParsedFile",
    "relative_path",
    "reset_config",
    "safe_parse",
    "save_baseline",
    "save_baseline_ids",
    "set_config",
    "__version__",
]
