"""Compatibility re-exports for the lint command package split."""

from __future__ import annotations

from slopgate.cli.lint.commands import (
    discover_project_root,
    lint_baseline,
    lint_check,
    lint_freeze,
    lint_init,
    lint_strict,
    lint_test_integrity,
    lint_update,
)

__all__ = [
    "discover_project_root",
    "lint_baseline",
    "lint_check",
    "lint_freeze",
    "lint_init",
    "lint_strict",
    "lint_test_integrity",
    "lint_update",
]
