"""Detectors for test-specific smells."""

from __future__ import annotations

import ast
from pathlib import Path
from vibeforcer.lint._baseline import Violation
from vibeforcer.lint._config import get_config
from vibeforcer.lint._helpers import (
    ParsedFile,
    ensure_parsed,
    find_test_files,
)


def _is_pytest_fixture_decorator(dec: ast.expr) -> bool:
    """True if *dec* looks like ``@pytest.fixture``, ``@pytest.fixture(...)``,
    or ``@fixture`` / ``@fixture(...)`` (when imported directly).
    """
    # @pytest.fixture
    if isinstance(dec, ast.Attribute):
        return (
            dec.attr == "fixture"
            and isinstance(dec.value, ast.Name)
            and dec.value.id == "pytest"
        )
    # @fixture  (from pytest import fixture)
    if isinstance(dec, ast.Name):
        return dec.id == "fixture"
    # @pytest.fixture(...) or @fixture(...)
    if isinstance(dec, ast.Call):
        return _is_pytest_fixture_decorator(dec.func)
    return False


def _is_fixture_support_module(path: Path) -> bool:
    """True for dedicated test fixture/support implementation modules."""
    normalized_parts = tuple(part.lower() for part in path.parts)
    return "_fixtures" in normalized_parts or "support" in normalized_parts


def detect_fixtures_outside_conftest(
    files: list[Path] | list[ParsedFile] | None = None,
) -> list[Violation]:
    """Find inline ``@pytest.fixture`` definitions in actual test modules.

    ``conftest.py`` remains the public pytest fixture registry. Dedicated
    support modules such as ``tests/<area>/_fixtures/*.py`` and
    ``tests/<area>/support/*.py`` may hold implementation-heavy fixtures so
    large test suites do not have to choose between this rule and module-size
    limits.
    """
    cfg = get_config()
    if not cfg.ban_fixtures_outside_conftest:
        return []

    parsed = ensure_parsed(files, fallback=find_test_files())
    violations: list[Violation] = []

    for pf in parsed:
        if pf.path.name == "conftest.py" or _is_fixture_support_module(pf.path):
            continue
        for node in ast.walk(pf.tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for dec in node.decorator_list:
                if _is_pytest_fixture_decorator(dec):
                    violations.append(
                        Violation(
                            rule="fixture-outside-conftest",
                            relative_path=pf.rel,
                            identifier=node.name,
                            detail=f"line {node.lineno}",
                        )
                    )
                    break
    return violations
