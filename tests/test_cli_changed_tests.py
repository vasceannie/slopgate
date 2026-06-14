"""Changed-test selector coverage for the ``slopgate test`` workflow."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from hypothesis import given, strategies

from slopgate.cli import changed_tests
from slopgate.cli.changed_tests import (
    DEFAULT_TEST_RUNNER,
    build_selection_index,
    changed_files_since,
    execute_selected_tests,
    normalize_changed_files,
    normalize_runner_args,
    parse_test_runner,
    select_tests_for_changed_files,
)
from slopgate.cli.changed_tests_parser import add_changed_test_parser
from slopgate.cli.commands import cmd_test
from slopgate.cli.io import CliInputError
from tests.cli_changed_tests_support import (
    minimal_selection_index,
    prepare_project,
    run_git,
    seed_git_project_with_added_modified_and_deleted_paths,
)

RUNNER_SENTINEL_EXIT = 7
PATH_TEXT = strategies.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789_./-", min_size=1, max_size=24
)


def test_selector_returns_tests_referencing_changed_symbol_and_module(
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare_project(tmp_project, monkeypatch)

    result = select_tests_for_changed_files(("src/pkg/core.py",))

    assert result.selected_tests == (
        "tests/test_core.py",
        "tests/test_module.py",
    ), "changed source should select symbol and module import tests"
    assert isinstance(result, changed_tests.TestSelectionResult), (
        "selector returns the public result type"
    )


def test_selector_ignores_non_python_and_unreferenced_source(
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare_project(tmp_project, monkeypatch)

    result = select_tests_for_changed_files(("README.md", "src/pkg/unused.py"))

    assert result.selected_tests == (), (
        "unreferenced and non-Python files select no tests"
    )


def test_changed_files_since_excludes_deleted_paths(tmp_project: Path) -> None:
    seed_git_project_with_added_modified_and_deleted_paths(tmp_project)

    changed = changed_files_since("HEAD", root=tmp_project)

    assert changed == (
        "src/pkg/added.py",
        "src/pkg/core.py",
    ), "deleted paths should be excluded from changed-test selection"


def test_changed_files_since_uses_merge_base_ref_syntax(
    monkeypatch: pytest.MonkeyPatch,
    tmp_project: Path,
) -> None:
    observed_command: list[str] = []
    completed = subprocess.CompletedProcess(
        args=("git", "diff"), returncode=0, stdout="src/pkg/core.py\n", stderr=""
    )

    def record_git_diff(
        command: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        observed_command.extend(command)
        return completed

    monkeypatch.setattr(changed_tests.subprocess, "run", record_git_diff)

    changed = changed_files_since("origin/main", root=tmp_project)

    assert changed == ("src/pkg/core.py",), "git-diff output should still be returned"
    assert observed_command[-1] == "origin/main...", (
        "changed-test selection should use git merge-base REF... semantics"
    )


def test_run_changed_test_workflow_returns_zero_when_no_tests_selected(
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    prepare_project(tmp_project, monkeypatch)
    request = changed_tests.TestSelectionRequest(
        since_ref=None,
        files=("README.md",),
        list_only=False,
        smoke=False,
        runner=DEFAULT_TEST_RUNNER,
        runner_args=(),
    )

    result = changed_tests.run_changed_test_workflow(request)
    captured = capsys.readouterr()

    assert result == 0, "no-match changed-test workflow should exit successfully"
    assert captured.out == "No impacted tests selected.\n", (
        "no-match changed-test workflow should explain that no tests were selected"
    )


def test_cmd_test_reports_bad_git_ref(
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    prepare_project(tmp_project, monkeypatch)
    run_git(tmp_project, "init")
    args = argparse.Namespace(
        smoke=False,
        since="missing-ref",
        files=None,
        list_only=False,
        runner=None,
        runner_args=[],
    )

    result = cmd_test(args)
    captured = capsys.readouterr()

    assert result == 1, "bad git refs should make cmd_test fail"
    assert "git diff failed for --since 'missing-ref'" in captured.err, (
        "bad git refs should report the failing --since value"
    )


def test_parse_test_runner_honors_default_and_shell_words() -> None:
    assert parse_test_runner("  ") == DEFAULT_TEST_RUNNER, (
        "blank runner should fall back to the documented pytest default"
    )
    assert parse_test_runner("python -m pytest --maxfail=1") == (
        "python",
        "-m",
        "pytest",
        "--maxfail=1",
    ), "runner strings should be parsed as shell words without shell execution"


def test_normalize_runner_args_removes_only_wrapper_separator() -> None:
    assert normalize_runner_args(("--", "--maxfail=1")) == ("--maxfail=1",), (
        "wrapper separator should not be forwarded to pytest"
    )
    assert normalize_runner_args(("-k", "core")) == ("-k", "core"), (
        "runner args without wrapper separator should pass through unchanged"
    )


def test_normalize_changed_files_deduplicates_and_relativizes(
    tmp_project: Path,
) -> None:
    absolute_core = tmp_project / "src" / "pkg" / "core.py"

    normalized = normalize_changed_files(
        (" ./src/pkg/core.py ", str(absolute_core), "README.md"), root=tmp_project
    )

    assert normalized == ("README.md", "src/pkg/core.py"), (
        "changed file normalization should produce unique repo-relative POSIX paths"
    )


def test_build_selection_index_exposes_project_symbols(
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare_project(tmp_project, monkeypatch)

    index = build_selection_index()

    assert any(
        symbol.relative_path == "src/pkg/core.py" for symbol in index.production_symbols
    ), "selection index should include discovered production symbols"


def test_execute_selected_tests_rejects_empty_runner() -> None:
    with pytest.raises(CliInputError):
        execute_selected_tests((), runner=(), runner_args=())


def test_execute_selected_tests_appends_runner_args_to_default_pytest(
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed_command: list[str] = []

    def record_pytest(
        command: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        observed_command.extend(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(changed_tests.subprocess, "run", record_pytest)

    result = execute_selected_tests(
        ("tests/test_core.py",),
        runner=DEFAULT_TEST_RUNNER,
        runner_args=("--maxfail=1",),
        root=tmp_project,
    )

    assert result == 0, "default pytest execution should return pytest's exit code"
    assert observed_command == [
        *DEFAULT_TEST_RUNNER,
        "tests/test_core.py",
        "--maxfail=1",
    ], "default pytest execution should preserve runner args after selected tests"


def test_add_changed_test_parser_registers_changed_test_options() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")

    add_changed_test_parser(subparsers)
    parsed = parser.parse_args(["test", "--list", "--files", "src/pkg/core.py"])

    assert (parsed.command, parsed.list_only, parsed.files) == (
        "test",
        True,
        ["src/pkg/core.py"],
    ), "parser registration should expose changed-test list and file options"


@given(path_text=PATH_TEXT)
def test_changed_files_since_sorts_nonblank_git_output_property(
    path_text: str,
) -> None:
    raw_paths = ("z.py", path_text, "a.py", "")
    expected_paths = tuple(sorted(path for path in raw_paths if path.strip()))
    completed = subprocess.CompletedProcess(
        args=("git", "diff"), returncode=0, stdout="\n".join(raw_paths), stderr=""
    )

    with patch.object(changed_tests.subprocess, "run", return_value=completed):
        changed = changed_files_since("HEAD", root=Path.cwd())

    assert changed == expected_paths, "changed_files_since should sort git-diff rows"


@given(path_text=PATH_TEXT)
def test_select_tests_for_changed_files_preserves_normalized_change_list_property(
    path_text: str,
) -> None:
    changed_path = path_text.strip() or "README.md"

    result = select_tests_for_changed_files(
        (changed_path, changed_path), index=minimal_selection_index()
    )
    expected_changed_files = normalize_changed_files((changed_path, changed_path))

    assert result.changed_files == expected_changed_files, (
        "selector should deduplicate normalized changed paths before matching tests"
    )


def test_cmd_test_list_mode_prints_selected_tests(
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    prepare_project(tmp_project, monkeypatch)
    args = argparse.Namespace(
        smoke=False,
        since=None,
        files=["src/pkg/core.py"],
        list_only=True,
        runner=None,
        runner_args=[],
    )

    result = cmd_test(args)
    captured = capsys.readouterr()

    assert result == 0, "list-only mode should exit successfully"
    assert captured.out == ("tests/test_core.py\ntests/test_module.py\n"), (
        "list-only mode should print selected tests"
    )


def test_changed_test_runner_appends_tests_before_extra_args(
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capfd: pytest.CaptureFixture[str],
) -> None:
    prepare_project(tmp_project, monkeypatch)
    runner_script = "import sys;print('|'.join(sys.argv[1:]));raise SystemExit(7)"
    request = changed_tests.TestSelectionRequest(
        since_ref=None,
        files=("src/pkg/core.py",),
        list_only=False,
        smoke=False,
        runner=(sys.executable, "-c", runner_script),
        runner_args=("--maxfail=1",),
    )

    result = changed_tests.run_changed_test_workflow(request)
    captured = capfd.readouterr()

    assert result == RUNNER_SENTINEL_EXIT, "runner exit code should propagate"
    assert captured.out == ("tests/test_core.py|tests/test_module.py|--maxfail=1\n"), (
        "runner args should be appended after selected tests"
    )
