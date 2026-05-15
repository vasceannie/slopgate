"""Verbose lint violation formatting and repair prognosis."""

from __future__ import annotations

import ast
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


def _project_file(relative_path: str) -> Path:
    try:
        from vibeforcer.lint._config import get_config

        return get_config().project_root / relative_path
    except Exception:
        return Path(relative_path)


def _truncate_preview(text: str, *, limit: int = 100) -> str:
    compact = " ".join(text.strip().split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _node_preview(node: ast.AST) -> str:
    try:
        return _truncate_preview(ast.unparse(node))
    except Exception:
        return type(node).__name__


def _function_name_from_identifier(identifier: str) -> str | None:
    name = identifier.split(":", maxsplit=1)[0]
    return name if name.startswith("test_") else None


def _find_test_node(
    tree: ast.AST,
    name: str | None,
    line_number: int | None,
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    candidates = [
        node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    ]
    if name is not None:
        for node in candidates:
            if node.name == name:
                return node
    if line_number is not None:
        for node in candidates:
            end_lineno = getattr(node, "end_lineno", node.lineno)
            if node.lineno <= line_number <= end_lineno:
                return node
    return None


def _assertion_context_lines(
    test_node: ast.FunctionDef | ast.AsyncFunctionDef | None,
) -> list[str]:
    if test_node is None:
        return []
    assertions: list[tuple[int, str]] = []
    for child in ast.walk(test_node):
        if isinstance(child, ast.Assert):
            assertions.append((child.lineno, _node_preview(child)))
            continue
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        name = ""
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        if name in _ASSERT_CALL_NAMES:
            assertions.append((child.lineno, _node_preview(child)))
    if not assertions:
        return []
    unique = sorted(dict(assertions).items())[:8]
    lines = ["    nearby-assertions:"]
    lines.extend(f"      line {line}: {preview}" for line, preview in unique)
    if len(assertions) > len(unique):
        lines.append(f"      ... +{len(assertions) - len(unique)} more")
    return lines


def _assertion_previews(
    test_node: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    limit: int = 3,
) -> list[str]:
    previews: list[tuple[int, str]] = []
    for child in ast.walk(test_node):
        if isinstance(child, ast.Assert):
            previews.append((child.lineno, _node_preview(child)))
            continue
        if not isinstance(child, ast.Call):
            continue
        func = child.func
        name = ""
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        if name in _ASSERT_CALL_NAMES:
            previews.append((child.lineno, _node_preview(child)))
    return [f"line {line}: {preview}" for line, preview in sorted(previews)[:limit]]


def _neighbor_test_context_lines(
    tree: ast.AST,
    test_node: ast.FunctionDef | ast.AsyncFunctionDef | None,
) -> list[str]:
    if test_node is None:
        return []
    tests = sorted(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        ),
        key=lambda node: node.lineno,
    )
    try:
        index = tests.index(test_node)
    except ValueError:
        return []
    neighbors = [
        node
        for neighbor_index in (index - 1, index + 1)
        if 0 <= neighbor_index < len(tests)
        for node in [tests[neighbor_index]]
    ]
    if not neighbors:
        return []
    lines = ["    neighboring-tests:"]
    for neighbor in neighbors:
        lines.append(f"      line {neighbor.lineno}: {neighbor.name}")
        for preview in _assertion_previews(neighbor, limit=2):
            lines.append(f"        {preview}")
    return lines


def _source_snippet_lines(path: Path, line_number: int | None) -> list[str]:
    if line_number is None or not path.exists() or not path.is_file():
        return []
    try:
        source_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    if not source_lines:
        return []
    start = max(1, line_number - 4)
    end = min(len(source_lines), line_number + 4)
    width = len(str(end))
    lines = ["    source-snippet:"]
    for current in range(start, end + 1):
        marker = ">" if current == line_number else " "
        text = source_lines[current - 1]
        lines.append(f"      {marker} {current:>{width}}|{text}")
    return lines


def _test_repair_context(rule_name: str, violation: Violation) -> list[str]:
    if rule_name == "untested-production-code":
        coverage_kind = violation.metadata.get("coverage_kind")
        coverage_note = (
            "    coverage-note: runtime coverage artifact was used; sort/fix by lowest line coverage first."
            if coverage_kind == "runtime-line"
            else "    coverage-note: no runtime coverage artifact was found, so this is static symbol-reference coverage."
        )
        return [
            coverage_note,
            "    correction-options: add behavior tests for the unreferenced public symbols, or delete/private-scope dead API if it is no longer production surface.",
            "    correction-options: prefer tests that assert observable behavior through the public entrypoint instead of importing every helper directly.",
            "    validation: .venv/bin/python -m pytest tests -q",
        ]
    if rule_name == "missing-integration-test":
        return [
            "    correction-options: add one thin integration/contract test through the real caller seam; stub only true outer boundaries.",
            "    required-proof: name the multi-caller production path and the final observable output/state that would fail if the seam regressed.",
            "    validation: .venv/bin/python -m pytest tests -q",
        ]
    if rule_name == "hypothesis-candidate":
        return [
            "    correction-options: add a small Hypothesis property for invariants, round-trips, idempotence, ordering, bounds, or malformed input handling.",
            "    correction-options: keep example tests for named regressions; use Hypothesis to explore the input space around them.",
            "    validation: .venv/bin/python -m pytest tests -q",
        ]
    if rule_name == "obsolete-or-deprecated-test":
        return [
            "    correction-options: update the test to the replacement production API, or delete it if it only preserves removed/deprecated behavior.",
            "    correction-options: if deprecated behavior must stay supported, assert the compatibility contract explicitly and link it to the migration path.",
            f"    validation: .venv/bin/python -m pytest {violation.relative_path} -q",
        ]
    if rule_name == "weak-test-assertion":
        return [
            "    correction-options: replace the presence check with exact content/state/output, or delete the test if neighboring assertions already prove the contract.",
            "    required-proof: write the sentence `this test would fail if <production seam/field> regressed because <assertion>` before editing.",
            f"    validation: .venv/bin/python -m pytest {violation.relative_path} -q",
        ]
    if rule_name == "mock-theater":
        return [
            "    correction-options: keep the mock only if it is an external boundary; otherwise use the real collaborator and assert output/state.",
            "    correction-options: if the mock stays, assert semantic args with assert_called_once_with/assert_has_calls and verify downstream observable behavior.",
            f"    validation: .venv/bin/python -m pytest {violation.relative_path} -q",
        ]
    if rule_name == "schema-bypass-test-data":
        return [
            "    correction-options: replace cast/SimpleNamespace fake models with the real constructor, factory, fixture, or a recorded protocol fixture.",
            "    repo-hint: inspect nearest conftest.py plus tests/**/_fixtures/ and tests/**/support/ before inventing a new helper.",
            f"    validation: .venv/bin/python -m pytest {violation.relative_path} -q",
        ]
    if rule_name == "hand-built-test-payload":
        return [
            "    correction-options: move large inline state/payload into a named fixture or recorded sample, then assert the parsed/rendered contract.",
            "    required-proof: name the schema or transformation layer that would reject/drop/blank this payload if it drifted.",
            f"    validation: .venv/bin/python -m pytest {violation.relative_path} -q",
        ]
    if rule_name == "mocked-integration-test":
        return [
            "    correction-options: unmock the internal parser/enrichment/store/handler/render seam; stub only the true outer boundary.",
            "    required-proof: feed realistic input through the real path and assert the final screen/output-facing value.",
            f"    validation: .venv/bin/python -m pytest {violation.relative_path} -q",
        ]
    return []


def _test_context_lines(rule_name: str, violation: Violation) -> list[str]:
    if rule_name not in _TEST_INTEGRITY_RULES:
        return []

    path = _project_file(violation.relative_path)
    line_number = _line_number(violation)
    lines = ["    agent-context:"]
    lines.extend(_source_snippet_lines(path, line_number))

    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)
    except (OSError, SyntaxError):
        tree = None
    if tree is not None:
        test_node = _find_test_node(
            tree,
            _function_name_from_identifier(violation.identifier),
            line_number,
        )
        if test_node is not None:
            lines.append(f"    test-under-review: {test_node.name}")
        lines.extend(_assertion_context_lines(test_node))
        lines.extend(_neighbor_test_context_lines(tree, test_node))

    lines.extend(_test_repair_context(rule_name, violation))
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
    if rule_name == "untested-production-code":
        return [
            "    prognosis: public production surface has low static test-reference coverage; this may be dead API or unprotected behavior.",
            "    scaffold: start with the lowest-coverage module, identify the public behavior users depend on, then add behavior/integration tests around that entrypoint.",
            "    verify: coverage here is static reference coverage; confirm with pytest-cov or an equivalent runtime coverage run before treating it as complete proof.",
        ]
    if rule_name == "missing-integration-test":
        return [
            "    prognosis: a production seam has multiple callers but no integration/e2e/pipeline test reference, so caller contract drift can hide between unit tests.",
            "    scaffold: build one realistic input through the real caller path and assert the final external state/output/event, not intermediate mocks.",
        ]
    if rule_name == "hypothesis-candidate":
        return [
            "    prognosis: this function has enough input/branch/transform surface that examples alone may miss edge cases.",
            "    scaffold: write a property around invariants such as round-trip, idempotence, monotonicity, bounds, rejected malformed input, or stable ordering.",
        ]
    if rule_name == "obsolete-or-deprecated-test":
        return [
            "    prognosis: test coverage may be protecting removed/deprecated behavior instead of current production contracts.",
            "    scaffold: migrate the test to the replacement API or keep it only as an explicit compatibility test with a deprecation/migration assertion.",
        ]
    if rule_name == "weak-test-assertion":
        return [
            "    prognosis: assertion proves presence or success shape, not the behavior a regression would break.",
            "    scaffold: assert exact user-visible output, parsed field values, persisted state, emitted event payloads, or fallback text.",
            "    verify: explain which broken production line/seam would make this assertion fail if reverted.",
        ]
    if rule_name == "mock-theater":
        return [
            "    prognosis: test mostly proves that a mock was called, not that real behavior survived the seam.",
            "    scaffold: mock only true external boundaries; assert semantic payloads or observable outputs, not called/call_count alone.",
            "    verify: run the test against the real parser/handler/store/render path where the bug can live.",
        ]
    if rule_name in {"schema-bypass-test-data", "hand-built-test-payload"}:
        return [
            "    prognosis: fake payload/model data can drift from the schema while tests keep passing.",
            "    scaffold: use real model constructors, factories, recorded wire payloads, or protocol fixtures instead of cast/raw dict fakes.",
            "    verify: assert the contract after parser/enrichment/projection transforms, not the hand-built intermediate shape.",
        ]
    if rule_name == "mocked-integration-test":
        return [
            "    prognosis: integration/e2e naming promises seam coverage, but internal mocks can sever the path where regressions hide.",
            "    scaffold: keep only outer-boundary stubs and exercise the real parser → enrichment → store/projection → handler → screen/output path.",
            "    verify: the test would fail if a transformation layer drops or blanks the target field.",
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
    lines.extend(_test_context_lines(rule_name, violation))
    lines.extend(_prognosis(rule_name, violation))
    return lines
