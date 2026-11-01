"""Eval package for offline redacted attempt-case packs."""

from __future__ import annotations

from .dataset import (
    EvalPackOptions,
    OverlayOutput,
    case_is_replayable,
    evaluate_case,
    evaluate_pack,
    load_eval_cases,
    summarize_eval,
)
from .overlay import OverlayProvenance, overlay_row_from_eval, write_overlay_jsonl

__all__ = [
    "EvalPackOptions",
    "OverlayOutput",
    "OverlayProvenance",
    "case_is_replayable",
    "evaluate_case",
    "evaluate_pack",
    "load_eval_cases",
    "overlay_row_from_eval",
    "summarize_eval",
    "write_overlay_jsonl",
]
