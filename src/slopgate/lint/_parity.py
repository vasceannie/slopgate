"""Machine-readable lint/baseline/hook parity contract.

This module is intentionally declarative: it does not decide enforcement by itself.
It exists so tests can fail loudly when a new lint collector or runtime hook rule is
added without an explicit coverage classification.
"""

from __future__ import annotations

from typing import Literal

ParityCategory = Literal[
    "baseline_lint",
    "focused_lint",
    "hook_preventive",
    "post_edit_backstop",
    "hook_operational_only",
    "config_safety_only",
]

COLLECTOR_CATEGORIES: dict[ParityCategory, frozenset[str]] = {
    "baseline_lint": frozenset(
        {
            "assertion-free-test",
            "assertion-roulette",
            "banned-any",
            "boundary-logging",
            "broad-except-swallow",
            "conditional-assertion",
            "deep-nesting",
            "deprecated-pattern",
            "dead-code",
            "direct-get-logger",
            "duplicate-call-sequence",
            "eager-test",
            "feature-envy",
            "fixture-outside-conftest",
            "flat-sibling-files",
            "god-class",
            "hand-built-test-payload",
            "high-complexity",
            "hypothesis-candidate",
            "import-alias",
            "import-fanout",
            "langgraph-deprecated-api",
            "langgraph-state-mutation",
            "langgraph-state-reducer",
            "long-line",
            "long-method",
            "long-test",
            "missing-integration-test",
            "mock-theater",
            "mocked-integration-test",
            "obsolete-or-deprecated-test",
            "oversized-module",
            "oversized-module-soft",
            "python-parse-error",
            "private-import-chain",
            "pytest-asyncio-pattern",
            "repeated-code-block",
            "repeated-magic-number",
            "repeated-string-literal",
            "schema-bypass-test-data",
            "semantic-clone",
            "silent-datetime-fallback",
            "silent-except",
            "too-many-params",
            "type-suppression",
            "unnecessary-wrapper",
            "untested-production-code",
            "weak-test-assertion",
            "wrong-logger-name",
        }
    ),
    "focused_lint": frozenset(),
    "hook_preventive": frozenset(),
    "post_edit_backstop": frozenset(),
    "hook_operational_only": frozenset(),
    "config_safety_only": frozenset(),
}

HOOK_RULE_CATEGORIES: dict[ParityCategory, frozenset[str]] = {
    "hook_preventive": frozenset(
        {
            "ERRORS-BASH-001",
            "ERRORS-FAIL-001",
            "FE-LINTER-001",
            "FE-LINTER-002",
            "BUILTIN-PROTECTED-PATHS",
            "GLOBAL-BUILTIN-HOOK-INFRA-EXEC",
            "GLOBAL-BUILTIN-SENSITIVE-DATA",
            "GLOBAL-BUILTIN-SYSTEM-PROTECTION",
            "LG-API-001",
            "LG-NODE-001",
            "LG-STATE-001",
            "PY-AST-001",
            "PY-AST-IMPORT-001",
            "PY-CODE-008",
            "PY-CODE-009",
            "PY-CODE-010",
            "PY-CODE-011",
            "PY-CODE-012",
            "PY-CODE-013",
            "PY-CODE-014",
            "PY-CODE-015",
            "PY-CODE-016",
            "PY-CODE-017",
            "PY-CODE-018",
            "PY-EXC-001",
            "PY-EXC-002",
            "PY-IMPORT-001",
            "PY-IMPORT-002",
            "PY-IMPORT-003",
            "PY-LOG-001",
            "PY-LOG-002",
            "PY-QUALITY-004",
            "PY-QUALITY-005",
            "PY-QUALITY-006",
            "PY-QUALITY-007",
            "PY-QUALITY-008",
            "PY-QUALITY-009",
            "PY-QUALITY-010",
            "PY-QUALITY-011",
            "PY-SHELL-001",
            "PY-TEST-001",
            "PY-TEST-002",
            "PY-TEST-003",
            "PY-TEST-004",
            "PY-TEST-005",
            "PY-TYPE-001",
            "PY-TYPE-002",
            "QUALITY-PROJECTED-LINT-001",
            "RS-QUALITY-001",
            "RS-QUALITY-002",
            "RS-QUALITY-003",
            "SHELL-001",
            "STYLE-004",
            "STYLE-005",
            "TS-LINT-001",
            "TS-LINT-002",
            "TS-QUALITY-003",
            "TS-TYPE-001",
            "TS-TYPE-002",
        }
    ),
    "post_edit_backstop": frozenset(
        {
            "QUALITY-LINT-001",
            "QUALITY-POST-001",
        }
    ),
    "hook_operational_only": frozenset(
        {
            "BUILTIN-ENFORCE-FULL-READ",
            "BUILTIN-INJECT-PROMPT",
            "GIT-001",
            "GIT-002",
            "GIT-003",
            "REMIND-PYTEST-MP",
            "REMIND-SEARCH-001",
            "REPO-ENROLL-001",
            "SESSION-001",
            "STOP-001",
            "STOP-002",
            "WARN-LARGE-001",
            "WORKFLOW-FIRST-WRITE-001",
        }
    ),
    "config_safety_only": frozenset(
        {
            "BASELINE-001",
            "BUILTIN-RULEBOOK-SECURITY",
            "CONFIG-001",
            "CONFIG-002",
            "CONFIG-003",
            "CONFIG-004",
            "CONFIG-005",
            "PY-LINTER-001",
            "PY-LINTER-002",
            "QA-PATH-001",
            "QA-PATH-002",
            "QA-PATH-003",
            "QA-PATH-004",
            "WARN-BASELINE-001",
            "WARN-BASELINE-002",
        }
    ),
    "baseline_lint": frozenset(),
    "focused_lint": frozenset(),
}

HOOK_RULE_BASELINE_COUNTERPARTS: dict[str, tuple[str, ...]] = {
    "PY-AST-001": ("python-parse-error",),
    "PY-CODE-008": ("long-method",),
    "PY-CODE-009": ("too-many-params",),
    "PY-CODE-010": ("long-line",),
    "PY-CODE-011": ("deep-nesting",),
    "PY-CODE-012": ("feature-envy",),
    "PY-CODE-013": ("unnecessary-wrapper",),
    "PY-CODE-014": ("god-class",),
    "PY-CODE-015": ("high-complexity",),
    "PY-CODE-016": ("dead-code",),
    "PY-CODE-017": ("flat-sibling-files",),
    "PY-CODE-018": ("oversized-module", "oversized-module-soft"),
    "PY-EXC-001": ("broad-except-swallow",),
    "PY-EXC-002": ("silent-datetime-fallback", "silent-except"),
    "PY-IMPORT-001": ("import-fanout",),
    "PY-IMPORT-002": ("import-alias",),
    "PY-IMPORT-003": ("private-import-chain",),
    "LG-API-001": ("langgraph-deprecated-api",),
    "LG-NODE-001": ("langgraph-state-mutation",),
    "LG-STATE-001": ("langgraph-state-reducer",),
    "PY-LOG-001": ("direct-get-logger", "wrong-logger-name"),
    "PY-LOG-002": ("boundary-logging",),
    "PY-QUALITY-010": ("repeated-magic-number",),
    "PY-TEST-001": ("assertion-roulette",),
    "PY-TEST-002": ("assertion-free-test", "eager-test", "long-test"),
    "PY-TEST-003": ("conditional-assertion",),
    "PY-TEST-004": ("fixture-outside-conftest",),
    "PY-TEST-005": ("pytest-asyncio-pattern",),
    "PY-TYPE-001": ("banned-any",),
    "PY-TYPE-002": ("type-suppression",),
    "QUALITY-LINT-001": tuple(sorted(COLLECTOR_CATEGORIES["baseline_lint"])),
}


def _classified_names(categories: dict[ParityCategory, frozenset[str]]) -> set[str]:
    names: set[str] = set()
    for category_names in categories.values():
        names.update(category_names)
    return names


def classified_collector_keys() -> set[str]:
    """Return every lint collector key declared in the parity contract."""
    return _classified_names(COLLECTOR_CATEGORIES)


def classified_hook_rule_ids() -> set[str]:
    """Return every hook/runtime rule id declared in the parity contract."""
    return _classified_names(HOOK_RULE_CATEGORIES)


def collector_category(rule_name: str) -> ParityCategory | None:
    """Return the declared category for a lint collector key."""
    for category, names in COLLECTOR_CATEGORIES.items():
        if rule_name in names:
            return category
    return None


def hook_rule_category(rule_id: str) -> ParityCategory | None:
    """Return the declared category for a runtime hook rule id."""
    for category, rule_ids in HOOK_RULE_CATEGORIES.items():
        if rule_id in rule_ids:
            return category
    return None
