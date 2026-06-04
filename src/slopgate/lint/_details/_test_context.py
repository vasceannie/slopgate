"""Test-integrity context rendering for lint details."""

from __future__ import annotations

import ast
from pathlib import Path

from slopgate.lint._baseline import Violation
from slopgate.lint._details._metadata import (
    _ASSERT_CALL_NAMES,
    _TEST_INTEGRITY_RULES,
    _line_number,
)

def _project_file(relative_path: str) -> Path:
    try:
        from slopgate.lint._config import get_config

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


_REPO_TEST_REPAIRS: dict[str, tuple[str, ...]] = {
    "missing-integration-test": (
        "    correction-options: add one thin integration/contract test through the real caller seam; stub only true outer boundaries.",
        "    required-proof: name the multi-caller production path and the final observable output/state that would fail if the seam regressed.",
        "    validation: .venv/bin/python -m pytest tests -q",
    ),
    "hypothesis-candidate": (
        "    correction-options: add a small Hypothesis property for invariants, round-trips, idempotence, ordering, bounds, or malformed input handling.",
        "    correction-options: keep example tests for named regressions; use Hypothesis to explore the input space around them.",
        "    validation: .venv/bin/python -m pytest tests -q",
    ),
}

_PATH_TEST_REPAIRS: dict[str, tuple[str, ...]] = {
    "obsolete-or-deprecated-test": (
        "    correction-options: update the test to the replacement production API, or delete it if it only preserves removed/deprecated behavior.",
        "    correction-options: if deprecated behavior must stay supported, assert the compatibility contract explicitly and link it to the migration path.",
    ),
    "weak-test-assertion": (
        "    correction-options: replace the presence check with exact content/state/output, or delete the test if neighboring assertions already prove the contract.",
        "    required-proof: write the sentence `this test would fail if <production seam/field> regressed because <assertion>` before editing.",
    ),
    "mock-theater": (
        "    correction-options: keep the mock only if it is an external boundary; otherwise use the real collaborator and assert output/state.",
        "    correction-options: if the mock stays, assert semantic args with assert_called_once_with/assert_has_calls and verify downstream observable behavior.",
    ),
    "schema-bypass-test-data": (
        "    correction-options: replace cast/SimpleNamespace fake models with the real constructor, factory, fixture, or a recorded protocol fixture.",
        "    repo-hint: inspect nearest conftest.py plus tests/**/_fixtures/ and tests/**/support/ before inventing a new helper.",
    ),
    "hand-built-test-payload": (
        "    correction-options: move large inline state/payload into a named fixture or recorded sample, then assert the parsed/rendered contract.",
        "    required-proof: name the schema or transformation layer that would reject/drop/blank this payload if it drifted.",
    ),
    "mocked-integration-test": (
        "    correction-options: unmock the internal parser/enrichment/store/handler/render seam; stub only the true outer boundary.",
        "    required-proof: feed realistic input through the real path and assert the final screen/output-facing value.",
    ),
}


def _path_pytest_validation(violation: Violation) -> str:
    return f"    validation: .venv/bin/python -m pytest {violation.relative_path} -q"


def _untested_production_repair_context(violation: Violation) -> list[str]:
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


def _test_repair_context(rule_name: str, violation: Violation) -> list[str]:
    if rule_name == "untested-production-code":
        return _untested_production_repair_context(violation)
    if rule_name in _REPO_TEST_REPAIRS:
        return list(_REPO_TEST_REPAIRS[rule_name])
    if rule_name in _PATH_TEST_REPAIRS:
        return [*_PATH_TEST_REPAIRS[rule_name], _path_pytest_validation(violation)]
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
