"""Prescriptive repair prognosis for lint detail blocks."""

from __future__ import annotations

from pathlib import Path

from slopgate.lint._baseline import Violation
from slopgate.lint._details.metadata import (
    BRANCH_RULES,
    DUPLICATE_RULES,
    EXCEPTION_RULES,
    LITERAL_RULES,
    TEST_RULES,
    TYPE_RULES,
)


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
        f"    scaffold: replace {path.as_posix()} with "
        f"{package.as_posix()}/__init__.py that re-exports the old public API.",
        "    scaffold: split focused concerns into "
        f"{package.as_posix()}/models.py, parsing.py, services.py, adapters.py, "
        "constants.py, and errors.py as applicable.",
        "    verify: preserve imports first, then move one responsibility at a time "
        "and run full repo lint from project root.",
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
    if rule_name in BRANCH_RULES:
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
    if rule_name in DUPLICATE_RULES:
        return [
            "    prognosis: duplicated behavior will drift unless the shared concept gets one owner.",
            "    scaffold: compare affected files first, extract the smallest shared helper/service, and keep call sites explicit.",
        ]
    if rule_name in LITERAL_RULES:
        return [
            "    prognosis: repeated literal is acting like unnamed policy or shared vocabulary.",
            "    scaffold: define an UPPER_CASE constant or resource entry near the owning domain, then replace all occurrences intentionally.",
        ]
    return None


_TYPE_OR_TEST_PROGNOSES: dict[str, tuple[str, ...]] = {
    "fixture-outside-conftest": (
        "    prognosis: fixture discovery and fixture implementation are mixed in the wrong place.",
        "    scaffold: expose fixtures through the narrowest conftest.py; move implementation helpers to tests/<area>/_fixtures/ or tests/<area>/support/.",
    ),
    "coverage-artifact-incomplete": (
        "    prognosis: the selected runtime coverage artifact is malformed, empty, or omits configured source modules.",
        "    scaffold: regenerate project-root coverage for every configured [paths].src root, then rerun the holistic integrity scan.",
    ),
    "untested-public-api": (
        "    prognosis: an intentionally exported Python surface lacks sufficient runtime or static coverage evidence.",
        "    scaffold: add an observable contract test through the exported facade, or remove the export if the surface is unintended.",
    ),
    "possibly-dead-internal": (
        "    prognosis: an unexported private-module symbol has no static caller or runtime coverage evidence, but reflection or registration may still use it.",
        "    scaffold: review callers, reflection, and registration before deleting or privatizing; do not add a test solely to mention the helper name.",
    ),
    "missing-integration-test": (
        "    prognosis: a production seam has multiple callers but no integration/e2e/pipeline test reference, so caller contract drift can hide between unit tests.",
        "    scaffold: build one realistic input through the real caller path and assert the final external state/output/event, not intermediate mocks.",
    ),
    "hypothesis-candidate": (
        "    prognosis: this function has enough input/branch/transform surface that examples alone may miss edge cases.",
        "    scaffold: keep finite named examples in pytest parametrize, then add a Hypothesis property for the broad invariant: round-trip, idempotence, monotonicity, bounds, rejected malformed input, no-crash parser behavior, or stable ordering.",
    ),
    "obsolete-or-deprecated-test": (
        "    prognosis: test coverage may be protecting removed/deprecated behavior instead of current production contracts.",
        "    scaffold: migrate the test to the replacement API or keep it only as an explicit compatibility test with a deprecation/migration assertion.",
    ),
    "weak-test-assertion": (
        "    prognosis: assertion proves presence or success shape, not the behavior a regression would break.",
        "    scaffold: assert exact user-visible output, parsed field values, persisted state, emitted event payloads, or fallback text.",
        "    verify: explain which broken production line/seam would make this assertion fail if reverted.",
    ),
    "mock-theater": (
        "    prognosis: test mostly proves that a mock was called, not that real behavior survived the seam.",
        "    scaffold: mock only true external boundaries; assert semantic payloads or observable outputs, not called/call_count alone.",
        "    verify: run the test against the real parser/handler/store/render path where the bug can live.",
    ),
    "schema-bypass-test-data": (
        "    prognosis: fake payload/model data can drift from the schema while tests keep passing.",
        "    scaffold: use real model constructors, factories, recorded wire payloads, or protocol fixtures instead of cast/raw dict fakes.",
        "    verify: assert the contract after parser/enrichment/projection transforms, not the hand-built intermediate shape.",
    ),
    "hand-built-test-payload": (
        "    prognosis: fake payload/model data can drift from the schema while tests keep passing.",
        "    scaffold: use real model constructors, factories, recorded wire payloads, or protocol fixtures instead of cast/raw dict fakes.",
        "    verify: assert the contract after parser/enrichment/projection transforms, not the hand-built intermediate shape.",
    ),
    "mocked-integration-test": (
        "    prognosis: integration/e2e naming promises seam coverage, but internal mocks can sever the path where regressions hide.",
        "    scaffold: keep only outer-boundary stubs and exercise the real parser → enrichment → store/projection → handler → screen/output path.",
        "    verify: the test would fail if a transformation layer drops or blanks the target field.",
    ),
}


def _type_or_test_prognosis(rule_name: str) -> list[str] | None:
    if rule_name in TYPE_RULES:
        return [
            "    prognosis: type boundary is being erased instead of modeled.",
            "    scaffold: replace Any/suppression with a Protocol, TypedDict, overload, local stub, or narrowed runtime validation.",
        ]
    if rule_name in _TYPE_OR_TEST_PROGNOSES:
        return list(_TYPE_OR_TEST_PROGNOSES[rule_name])
    if rule_name in TEST_RULES:
        return [
            "    prognosis: test intent is not isolated enough for readable failure diagnosis.",
            "    scaffold: split one behavior per test, parametrize cases with ids, and make each assertion describe the contract being checked.",
        ]
    return None


def _exception_prognosis(rule_name: str) -> list[str] | None:
    if rule_name in EXCEPTION_RULES:
        return [
            "    prognosis: error path hides failures that should be observable.",
            "    scaffold: catch the specific expected exception, log/return structured context, and let corruption or infrastructure failures propagate.",
        ]
    return None


def prognosis(rule_name: str, violation: Violation) -> list[str]:
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
