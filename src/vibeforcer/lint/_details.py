"""Verbose lint violation formatting and repair prognosis."""

from __future__ import annotations

import re
from pathlib import Path
from typing import cast

from vibeforcer._types import ObjectDict
from vibeforcer.lint._baseline import Violation

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
}
_EXCEPTION_RULES = {"broad-except-swallow", "silent-except", "silent-datetime-fallback"}


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


def _module_split_scaffold(violation: Violation) -> list[str]:
    path = Path(violation.relative_path)
    if path.name == "conftest.py":
        support_dir = path.parent / "_fixtures"
        return [
            "    prognosis: split fixture implementation out of conftest while keeping discovery thin.",
            f"    scaffold: keep {path.as_posix()} as a registry/import surface.",
            f"    scaffold: move fixture builders/helpers into {support_dir.as_posix()}/ or {(path.parent / 'support').as_posix()}/.",
            "    verify: import the fixtures through conftest and run the full repo lint from project root.",
        ]
    if path.name == "__init__.py":
        return [
            "    prognosis: package initializer is carrying implementation weight.",
            f"    scaffold: keep {path.as_posix()} as a facade with __all__ and compatibility re-exports only.",
            "    scaffold: move implementation into sibling modules such as models.py, parsing.py, services.py, adapters.py, and constants.py.",
        ]
    package = path.with_suffix("")
    return [
        "    prognosis: one module owns multiple responsibilities; convert it to a package split.",
        f"    scaffold: replace {path.as_posix()} with {package.as_posix()}/__init__.py that re-exports the old public API.",
        f"    scaffold: split focused concerns into {package.as_posix()}/models.py, parsing.py, services.py, adapters.py, constants.py, and errors.py as applicable.",
        "    verify: preserve imports first, then move one responsibility at a time and run full repo lint from project root.",
    ]


def _default_prognosis() -> list[str]:
    return [
        "    prognosis: smell needs an explicit owner and a focused repair before feature work continues.",
        "    scaffold: reread the affected file, fix this rule's specific signature, then run full repo lint from project root.",
    ]


def _structural_prognosis(rule_name: str) -> list[str] | None:
    if rule_name == "god-class":
        return [
            "    prognosis: class has too many responsibilities or too much body span.",
            "    scaffold: group methods by state they mutate and collaborators they call; extract composed collaborator classes around those groups.",
            "    scaffold: leave a small facade only if external API compatibility requires it.",
        ]
    if rule_name == "long-method":
        return [
            "    prognosis: function is doing multiple phases inline.",
            "    scaffold: extract named helpers for parse/validate/transform/persist/render phases; keep data flow explicit.",
        ]
    if rule_name in _BRANCH_RULES:
        return [
            "    prognosis: branching shape is hiding the domain decision table.",
            "    scaffold: use guard clauses, named predicates, or a dispatch table before adding behavior.",
        ]
    if rule_name == "too-many-params":
        return [
            "    prognosis: call boundary is carrying an unmodeled concept.",
            "    scaffold: introduce a dataclass, TypedDict, or params object only for fields that travel together semantically.",
        ]
    return None


def _duplicate_or_literal_prognosis(rule_name: str) -> list[str] | None:
    if rule_name in _DUPLICATE_RULES:
        return [
            "    prognosis: duplicated behavior will drift unless the shared concept gets one owner.",
            "    scaffold: compare affected files first, extract the smallest shared helper/service, and keep call sites explicit.",
        ]
    if rule_name in _LITERAL_RULES:
        return [
            "    prognosis: repeated literal is acting like unnamed policy or shared vocabulary.",
            "    scaffold: define an UPPER_CASE constant or resource entry near the owning domain, then replace all occurrences intentionally.",
        ]
    return None


def _type_or_test_prognosis(rule_name: str) -> list[str] | None:
    if rule_name in _TYPE_RULES:
        return [
            "    prognosis: type boundary is being erased instead of modeled.",
            "    scaffold: replace Any/suppression with a Protocol, TypedDict, overload, local stub, or narrowed runtime validation.",
        ]
    if rule_name == "fixture-outside-conftest":
        return [
            "    prognosis: fixture discovery and fixture implementation are mixed in the wrong place.",
            "    scaffold: expose fixtures through the narrowest conftest.py; move implementation helpers to tests/<area>/_fixtures/ or tests/<area>/support/.",
        ]
    if rule_name in _TEST_RULES:
        return [
            "    prognosis: test intent is not isolated enough for readable failure diagnosis.",
            "    scaffold: split one behavior per test, parametrize cases with ids, and make each assertion describe the contract being checked.",
        ]
    return None


def _exception_prognosis(rule_name: str) -> list[str] | None:
    if rule_name in _EXCEPTION_RULES:
        return [
            "    prognosis: error path hides failures that should be observable.",
            "    scaffold: catch the specific expected exception, log/return structured context, and let corruption or infrastructure failures propagate.",
        ]
    return None


def _prognosis(rule_name: str, violation: Violation) -> list[str]:
    if rule_name in {"oversized-module", "oversized-module-soft"}:
        return _module_split_scaffold(violation)
    for provider in (
        _structural_prognosis,
        _duplicate_or_literal_prognosis,
        _type_or_test_prognosis,
        _exception_prognosis,
    ):
        prognosis = provider(rule_name)
        if prognosis is not None:
            return prognosis
    return _default_prognosis()


def format_violation_details(
    rule_name: str,
    violation: Violation,
    *,
    status: str,
) -> list[str]:
    """Return an extended, prescriptive block for one lint violation."""

    lines = [
        f"    [{status}] {rule_name}",
        f"    file: {violation.relative_path}",
        f"    location: {_location(violation)}",
        f"    signature: {_signature(rule_name, violation)}",
    ]
    if violation.detail:
        lines.append(f"    detail: {violation.detail}")
    lines.append(f"    stable-id: {violation.stable_id}")
    lines.extend(_metadata_lines(violation.metadata))
    lines.extend(_prognosis(rule_name, violation))
    return lines
