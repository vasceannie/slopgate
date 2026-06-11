"""Compatibility re-exports for the lint report package split."""

from __future__ import annotations

from slopgate.cli.lint.report import (
    BASELINE_DISABLED_MESSAGE,
    BaselineInputs,
    LintFiles,
    LintGateMode,
    LintHeader,
    LintRunTotals,
    TallyInput,
    print_collector_results,
    print_lint_header,
    print_lint_summary,
    tally_rule,
)

__all__ = [
    "BASELINE_DISABLED_MESSAGE",
    "BaselineInputs",
    "LintFiles",
    "LintGateMode",
    "LintHeader",
    "LintRunTotals",
    "TallyInput",
    "print_collector_results",
    "print_lint_header",
    "print_lint_summary",
    "tally_rule",
]
