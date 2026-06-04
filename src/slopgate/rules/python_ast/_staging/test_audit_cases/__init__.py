"""Case data for staging hook-rule audit tests."""

from __future__ import annotations

from vibeforcer.rules.python_ast._staging.test_audit_cases._duplicate import _DUPLICATE_RULE_CASES
from vibeforcer.rules.python_ast._staging.test_audit_cases._smells import _TEST_SMELL_RULE_CASES
from vibeforcer.rules.python_ast._staging.test_audit_cases._stability import (
    _ALL_STAGING_RULES,
    _STABILITY_SOURCES,
)

__all__ = [
    "_ALL_STAGING_RULES",
    "_DUPLICATE_RULE_CASES",
    "_STABILITY_SOURCES",
    "_TEST_SMELL_RULE_CASES",
]
