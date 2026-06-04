"""Location, signature, and metadata formatting helpers for lint details."""

from __future__ import annotations

import re
from typing import cast

from slopgate._types import ObjectDict
from slopgate.lint._baseline import Violation

_LINE_RE = re.compile(r"\bline(?:s)?[ =:-]*(\d+)(?:\s*[-:]\s*(\d+))?", re.IGNORECASE)

_CALLABLE_RULES = {
    "high-complexity",
    "long-method",
    "too-many-params",
    "deep-nesting",
    "long-test",
    "eager-test",
    "assertion-free-test",
    "assertion-roulette",
    "conditional-assertion",
}
_BRANCH_RULES = {"high-complexity", "deep-nesting"}
_DUPLICATE_RULES = {"semantic-clone", "repeated-code-block", "duplicate-call-sequence"}
_LITERAL_RULES = {"repeated-magic-number", "repeated-string-literal"}
_TYPE_RULES = {"banned-any", "type-suppression"}
_TEST_RULES = {
    "long-test",
    "eager-test",
    "assertion-free-test",
    "assertion-roulette",
    "conditional-assertion",
    "untested-production-code",
    "missing-integration-test",
    "hypothesis-candidate",
    "obsolete-or-deprecated-test",
    "weak-test-assertion",
    "mock-theater",
    "schema-bypass-test-data",
    "hand-built-test-payload",
    "mocked-integration-test",
}
_TEST_INTEGRITY_RULES = {
    "untested-production-code",
    "missing-integration-test",
    "hypothesis-candidate",
    "obsolete-or-deprecated-test",
    "weak-test-assertion",
    "mock-theater",
    "schema-bypass-test-data",
    "hand-built-test-payload",
    "mocked-integration-test",
}
_EXCEPTION_RULES = {"broad-except-swallow", "silent-except", "silent-datetime-fallback"}
_ASSERT_CALL_NAMES = {
    "assertEqual",
    "assertIn",
    "assertIs",
    "assertIsNotNone",
    "assertTrue",
    "assertFalse",
    "assertGreater",
    "assertLess",
    "assertRegex",
    "assertNotEqual",
    "assert_called",
    "assert_called_once",
    "assert_called_with",
    "assert_called_once_with",
    "assert_any_call",
    "assert_has_calls",
    "assert_not_called",
}


def _line_hint(violation: Violation) -> str | None:
    identifier = violation.identifier
    if identifier.startswith("line-"):
        suffix = identifier.removeprefix("line-")
        if suffix.isdigit():
            return suffix
    match = _LINE_RE.search(violation.detail)
    if match is None:
        return None
    start = match.group(1)
    end = match.group(2)
    return f"{start}-{end}" if end else start


def _line_number(violation: Violation) -> int | None:
    hint = _line_hint(violation)
    if hint is None:
        return None
    first = hint.split("-", maxsplit=1)[0]
    if not first.isdigit():
        return None
    return int(first)


def _location(violation: Violation) -> str:
    line_hint = _line_hint(violation)
    if line_hint:
        return f"{violation.relative_path}:{line_hint}"
    return violation.relative_path


def _signature(rule_name: str, violation: Violation) -> str:
    identifier = violation.identifier
    if rule_name in _CALLABLE_RULES:
        return f"callable `{identifier}`"
    if rule_name == "god-class":
        return f"class `{identifier}`"
    if rule_name in {"oversized-module", "oversized-module-soft"}:
        return f"module `{identifier}`"
    if rule_name in {"semantic-clone", "duplicate-call-sequence"}:
        return f"duplicate signature `{identifier}`"
    if rule_name in _LITERAL_RULES:
        return f"literal `{identifier}`"
    return f"identifier `{identifier}`"


def _flatten_metadata(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (int, float, bool)):
        return [str(value)]
    if isinstance(value, (list, tuple, set)):
        items: list[str] = []
        iterable = cast(list[object] | tuple[object, ...] | set[object], value)
        for item in iterable:
            items.extend(_flatten_metadata(item))
        return items
    if isinstance(value, dict):
        items = []
        for key, item in cast(dict[object, object], value).items():
            nested = _flatten_metadata(item)
            if nested:
                items.extend(f"{key}: {entry}" for entry in nested)
        return items
    return []


def _metadata_lines(metadata: ObjectDict) -> list[str]:
    if not metadata:
        return []
    lines: list[str] = []
    for key in sorted(metadata):
        values = _flatten_metadata(metadata[key])
        if not values:
            continue
        preview = ", ".join(values[:6])
        if len(values) > 6:
            preview += f", ... +{len(values) - 6} more"
        lines.append(f"    metadata.{key}: {preview}")
    return lines
