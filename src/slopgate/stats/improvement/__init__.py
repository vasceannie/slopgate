"""Canonical improvement measurement for Slopgate stats.

Public API: :func:`build_improvement` assembles the nested versioned
improvement object, :class:`ComparisonSpec` plus :func:`build_comparison`
power guarded baseline/candidate reports, and the scope/episode helpers are
re-exported for tests and the dashboard parity mirror.
"""

from __future__ import annotations

from .comparison import (
    COMPARISON_DIMENSIONS,
    ComparisonRequest,
    ComparisonSpec,
    apply_cohort_filters,
    build_comparison,
    parse_cohort_filters,
    resolve_comparison,
)
from .episodes import evaluate_episodes, evaluate_first_observed, parse_result_records
from .metrics import IMPROVEMENT_SCHEMA_VERSION, build_improvement
from .scope_model import (
    EPISODE_TERMINAL_STATES,
    PATHLESS_SENTINEL,
    ResultRecord,
    RepairEpisode,
    EpisodeEvaluation,
    normalize_target_path,
    semantic_tool_family,
)

__all__ = [
    "COMPARISON_DIMENSIONS",
    "ComparisonRequest",
    "ComparisonSpec",
    "EPISODE_TERMINAL_STATES",
    "EpisodeEvaluation",
    "IMPROVEMENT_SCHEMA_VERSION",
    "PATHLESS_SENTINEL",
    "RepairEpisode",
    "ResultRecord",
    "apply_cohort_filters",
    "build_comparison",
    "build_improvement",
    "evaluate_episodes",
    "evaluate_first_observed",
    "normalize_target_path",
    "parse_cohort_filters",
    "parse_result_records",
    "resolve_comparison",
    "semantic_tool_family",
]

