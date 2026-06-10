"""Case data for staging hook-rule audit tests."""

from __future__ import annotations

__all__ = [
    "ALL_STAGING_RULES",
    "DUPLICATE_RULE_CASES",
    "STABILITY_SOURCES",
    "TEST_SMELL_RULE_CASES",
]

from slopgate.rules.python_ast._staging.test_audit_cases._duplicate import (
    DUPLICATE_RULE_CASES,
)
from slopgate.rules.python_ast._staging.test_audit_cases._smells import (
    TEST_SMELL_RULE_CASES,
)
from slopgate.rules.python_ast._staging.test_audit_cases._stability import (
    ALL_STAGING_RULES,
    STABILITY_SOURCES,
)

__all__ = [
    "ALL_STAGING_RULES",
    "DUPLICATE_RULE_CASES",
    "STABILITY_SOURCES",
    "TEST_SMELL_RULE_CASES",
]
