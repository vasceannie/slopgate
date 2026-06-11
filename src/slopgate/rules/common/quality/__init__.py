"""Quality-related common hook rules."""

from __future__ import annotations

from .guidance import (
    DEFAULT_SPLIT_DETAIL,
    OVERSIZED_LINT_RULES,
    SPLIT_SCENARIO_DETAILS,
    first_lint_path,
    has_oversized_module_failure,
    lint_check_instruction,
    lint_split_scenario,
    lint_target_summary,
    post_lint_oversized_guidance,
    post_lint_split_detail,
)
from .lint import (
    PostEditLintRule,
    SearchReminderRule,
    collect_touched_lint_failures,
    python_lint_targets,
    resolve_python_candidates,
)
from .postedit import (
    PostEditQualityRule,
    QualityCommandFailure,
    collect_quality_commands,
    run_quality_commands,
)

__all__ = [
    "DEFAULT_SPLIT_DETAIL",
    "OVERSIZED_LINT_RULES",
    "SPLIT_SCENARIO_DETAILS",
    "PostEditLintRule",
    "PostEditQualityRule",
    "QualityCommandFailure",
    "SearchReminderRule",
    "collect_quality_commands",
    "collect_touched_lint_failures",
    "first_lint_path",
    "has_oversized_module_failure",
    "lint_check_instruction",
    "lint_split_scenario",
    "lint_target_summary",
    "post_lint_oversized_guidance",
    "post_lint_split_detail",
    "python_lint_targets",
    "resolve_python_candidates",
    "run_quality_commands",
]
