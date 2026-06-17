"""Support helpers for changed-test CLI behavior tests."""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

from slopgate.lint._config import reset_config
from slopgate.lint._detectors.test_smells import IntegrityIndex, ProductionSymbol
from slopgate.lint._helpers import ParsedFile

GIT_TEST_USER_EMAIL = "slopgate-tests@example.invalid"
GIT_TEST_USER_NAME = "Slopgate Tests"


def write_selector_project(root: Path) -> None:
    (root / "slopgate.toml").write_text(
        "[slopgate]\nenabled = true\n", encoding="utf-8"
    )
    package = root / "src" / "pkg"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "core.py").write_text(
        'def used() -> str:\n    return "used"\n\n\ndef unreferenced() -> str:\n    return "no"\n',
        encoding="utf-8",
    )
    (package / "unused.py").write_text(
        'def orphan() -> str:\n    return "orphan"\n',
        encoding="utf-8",
    )
    tests = root / "tests"
    tests.mkdir()
    (tests / "test_core.py").write_text(
        'from pkg.core import used\n\n\ndef test_used() -> None:\n    assert used() == "used"\n',
        encoding="utf-8",
    )
    (tests / "test_module.py").write_text(
        'import pkg.core\n\n\ndef test_module_import() -> None:\n    assert pkg.core.used() == "used"\n',
        encoding="utf-8",
    )


def prepare_project(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write_selector_project(root)
    monkeypatch.chdir(root)
    reset_config()


def run_git(repo: Path, *args: str, test_identity: bool = False) -> None:
    command = ["git", "-C", str(repo)]
    if test_identity:
        command.extend(
            [
                "-c",
                f"user.email={GIT_TEST_USER_EMAIL}",
                "-c",
                f"user.name={GIT_TEST_USER_NAME}",
            ]
        )
    command.extend(args)
    subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def minimal_selection_index() -> IntegrityIndex:
    source: str = 'def used() -> str:\n    return "used"\n'
    source_lines = source.splitlines()
    parsed_source = ParsedFile(
        path=Path("src/pkg/core.py"),
        rel="src/pkg/core.py",
        tree=ast.parse(source),
        lines=source_lines,
        parent_map={},
        string_line_ranges=set(),
    )
    symbol = ProductionSymbol(
        name="used",
        qualname="pkg.core.used",
        module="pkg.core",
        relative_path="src/pkg/core.py",
        lineno=1,
        kind="function",
        parameter_count=0,
        branch_score=0,
        transform_score=0,
        deprecated=False,
        replacement=None,
    )
    return IntegrityIndex(
        parsed_src=[parsed_source],
        parsed_tests=[],
        production_symbols=[symbol],
        test_reference_tokens={"used", "pkg.core"},
        test_reference_tokens_by_rel={
            "tests/test_core.py": {"used"},
            "tests/test_module.py": {"pkg.core"},
        },
        integration_test_reference_tokens=set(),
        production_call_sites={},
        module_names={"pkg.core"},
        hypothesis_reference_tokens=set(),
        deprecated_symbols=[],
    )


def seed_git_project_with_added_modified_and_deleted_paths(root: Path) -> None:
    write_selector_project(root)
    run_git(root, "init")
    run_git(root, "add", ".")
    run_git(root, "commit", "-m", "seed", test_identity=True)
    (root / "src" / "pkg" / "core.py").write_text(
        'def used() -> str:\n    return "changed"\n', encoding="utf-8"
    )
    (root / "src" / "pkg" / "unused.py").unlink()
    (root / "src" / "pkg" / "added.py").write_text(
        'def added() -> str:\n    return "added"\n', encoding="utf-8"
    )
    run_git(root, "add", "src/pkg/added.py")
