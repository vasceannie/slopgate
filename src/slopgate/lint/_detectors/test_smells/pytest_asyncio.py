"""pytest-asyncio repository detectors."""

from __future__ import annotations

import ast
from collections.abc import Sequence
from pathlib import Path

from slopgate.lint._baseline import Violation
from slopgate.lint._config import get_config
from slopgate.lint._helpers import ParsedFile, ensure_parsed, find_test_files
from slopgate.rules.python_ast._pytest_asyncio_ast import (
    FixtureCheckTarget,
    fixture_decorator_call,
    fixture_decorator_name,
    has_async_backend_mark,
    iter_async_tests,
    pytest_aliases,
    string_keyword,
)
from slopgate.rules.python_ast._pytest_asyncio_config import (
    PytestAsyncioConfig,
    pytest_config_for_root,
)
from slopgate.rules.python_ast._pytest_asyncio_fixture_scope import is_pytest_path
from slopgate.rules.python_ast._pytest_asyncio_scope import (
    is_unknown_fixture_scope,
    is_valid_fixture_loop_scope,
)


def _pytest_asyncio_config() -> PytestAsyncioConfig:
    return pytest_config_for_root(str(get_config().project_root))


def _violation(
    parsed_file: ParsedFile,
    node: ast.AsyncFunctionDef,
    detail: str,
) -> Violation:
    return Violation(
        rule="pytest-asyncio-pattern",
        relative_path=parsed_file.rel,
        identifier=node.name,
        detail=f"{detail} line={node.lineno}",
    )


def _async_test_violations(parsed_file: ParsedFile) -> list[Violation]:
    if _pytest_asyncio_config().mode == "auto":
        return []
    aliases = pytest_aliases(parsed_file.tree)
    violations: list[Violation] = []
    for candidate in iter_async_tests(parsed_file.tree):
        node = candidate.node
        if candidate.has_context_mark or has_async_backend_mark(
            node.decorator_list, aliases
        ):
            continue
        violations.append(_violation(parsed_file, node, "missing-asyncio-mark"))
    return violations


def _fixture_scope_violation(
    parsed_file: ParsedFile,
    target: FixtureCheckTarget,
) -> Violation | None:
    call = target.call
    scope = string_keyword(call, "scope") if call is not None else None
    loop_scope = string_keyword(call, "loop_scope") if call is not None else None
    configured_loop_scope = _pytest_asyncio_config().default_fixture_loop_scope
    effective_loop_scope = loop_scope or configured_loop_scope
    if is_unknown_fixture_scope(scope):
        return _violation(parsed_file, target.node, f"unknown-scope={scope}")
    if is_unknown_fixture_scope(effective_loop_scope):
        return _violation(
            parsed_file,
            target.node,
            f"unknown-loop-scope={effective_loop_scope}",
        )
    if is_valid_fixture_loop_scope(scope, effective_loop_scope):
        return None
    fixture_scope = scope or "function"
    return _violation(parsed_file, target.node, f"loop-scope<{fixture_scope}")


def _async_fixture_violations(parsed_file: ParsedFile) -> list[Violation]:
    auto_mode = _pytest_asyncio_config().mode == "auto"
    aliases = pytest_aliases(parsed_file.tree)
    violations: list[Violation] = []
    for node in ast.walk(parsed_file.tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        fixture_name = fixture_decorator_name(node, aliases)
        if fixture_name is None:
            continue
        if fixture_name == "pytest.fixture" and not auto_mode:
            violations.append(_violation(parsed_file, node, "plain-async-fixture"))
            continue
        target = FixtureCheckTarget(
            parsed_file.rel,
            node,
            fixture_decorator_call(node, aliases),
            aliases,
        )
        if (violation := _fixture_scope_violation(parsed_file, target)) is not None:
            violations.append(violation)
    return violations


def detect_pytest_asyncio_patterns(
    files: Sequence[Path | ParsedFile] | None = None,
) -> list[Violation]:
    """Find pytest-asyncio patterns that are unsafe for the project config."""
    violations: list[Violation] = []
    for parsed_file in ensure_parsed(files, fallback=find_test_files()):
        if not is_pytest_path(parsed_file.rel):
            continue
        violations.extend(_async_test_violations(parsed_file))
        violations.extend(_async_fixture_violations(parsed_file))
    return violations
