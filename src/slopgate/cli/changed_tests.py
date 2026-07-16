"""Changed-test selection for the ``slopgate test`` CLI workflow."""

from __future__ import annotations

import shlex
import subprocess
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from slopgate.cli.io import CliInputError
from slopgate.cli.js_ts_tests import (
    changed_files_in_submodules,
    execute_default_js_ts_tests,
    is_js_ts_test_path,
    select_js_ts_tests,
)
from slopgate.lint import find_source_files, find_test_files, get_config
from slopgate.lint._detectors.test_smells import (
    IntegrityIndex,
    ProductionSymbol,
    build_test_integrity_index,
    module_name_from_rel,
    symbol_is_referenced,
)

DEFAULT_SINCE_REF = "HEAD"
DEFAULT_TEST_RUNNER = ("python", "-m", "pytest", "-n", "auto", "-v", "--tb=short")


@dataclass(frozen=True)
class TestSelectionRequest:
    since_ref: str | None
    files: tuple[str, ...]
    list_only: bool
    smoke: bool
    runner: tuple[str, ...]
    runner_args: tuple[str, ...]


@dataclass(frozen=True)
class TestSelectionResult:
    changed_files: tuple[str, ...]
    selected_tests: tuple[str, ...]


def parse_test_runner(raw_runner: str) -> tuple[str, ...]:
    """Parse a shell-style runner prefix without executing through a shell."""

    if not raw_runner.strip():
        return DEFAULT_TEST_RUNNER
    runner = tuple(shlex.split(raw_runner))
    if not runner:
        raise CliInputError("--runner must not be empty")
    return runner


def normalize_runner_args(raw_args: tuple[str, ...]) -> tuple[str, ...]:
    """Drop the Slopgate-level ``--`` separator before invoking pytest."""

    if raw_args[:1] == ("--",):
        return raw_args[1:]
    return raw_args


def project_root() -> Path:
    """Return the configured project root for test selection."""

    return get_config().project_root


def changed_files_since(since_ref: str, *, root: Path | None = None) -> tuple[str, ...]:
    """Return added, modified, or renamed git paths since ``since_ref``."""

    cwd = root or project_root()
    diff_ref = since_ref if since_ref == DEFAULT_SINCE_REF else f"{since_ref}..."
    try:
        completed = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=AMR", diff_ref],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        raise CliInputError(
            "git executable was not found for changed-test selection"
        ) from exc
    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        detail = f": {stderr}" if stderr else ""
        raise CliInputError(f"git diff failed for --since {since_ref!r}{detail}")
    changed_files = [path for path in completed.stdout.splitlines() if path.strip()]
    if since_ref == DEFAULT_SINCE_REF:
        changed_files.extend(changed_files_in_submodules(cwd, since_ref))
    return tuple(sorted(changed_files))


def normalize_changed_files(
    changed_files: Iterable[str], *, root: Path | None = None
) -> tuple[str, ...]:
    """Normalize changed file paths to sorted repo-relative POSIX strings."""

    base = (root or project_root()).resolve()
    normalized: set[str] = set()
    for raw in changed_files:
        path_text = raw.strip()
        if not path_text:
            continue
        path = Path(path_text)
        if path.is_absolute():
            try:
                relative = path.resolve().relative_to(base)
            except ValueError:
                relative = path
        else:
            relative = path
        normalized.add(relative.as_posix().removeprefix("./"))
    return tuple(sorted(normalized))


def build_selection_index() -> IntegrityIndex:
    """Build the shared integrity index with explicit source discovery."""

    return build_test_integrity_index(find_source_files(), find_test_files())


def select_tests_for_changed_files(
    changed_files: Iterable[str], *, index: IntegrityIndex | None = None
) -> TestSelectionResult:
    """Select tests whose reference tokens mention changed source symbols/modules."""

    normalized_changed_files = normalize_changed_files(changed_files)
    integrity_index = index or build_selection_index()
    source_paths = {parsed.rel for parsed in integrity_index.parsed_src}
    changed_python_sources = tuple(
        path
        for path in normalized_changed_files
        if path.endswith(".py") and path in source_paths
    )
    changed_source_set = set(changed_python_sources)
    changed_symbols = tuple(
        symbol
        for symbol in integrity_index.production_symbols
        if symbol.relative_path in changed_source_set
    )
    changed_modules = {
        module_name
        for path in changed_python_sources
        for module_name in [module_name_from_rel(path).lower()]
        if module_name
    }
    selected_tests = tuple(
        sorted(
            test_path
            for test_path, tokens in integrity_index.test_reference_tokens_by_rel.items()
            if _test_tokens_match_changed_source(
                tokens, changed_symbols, changed_modules
            )
        )
    )
    selected_tests = tuple(
        sorted(
            {
                *selected_tests,
                *select_js_ts_tests(normalized_changed_files, root=project_root()),
            }
        )
    )
    return TestSelectionResult(
        changed_files=normalized_changed_files,
        selected_tests=selected_tests,
    )


def execute_selected_tests(
    selected_tests: Sequence[str],
    *,
    runner: Sequence[str],
    runner_args: Sequence[str],
    root: Path | None = None,
) -> int:
    """Execute the configured test runner with selected tests appended."""

    if not runner:
        raise CliInputError("--runner must not be empty")
    if tuple(runner) == DEFAULT_TEST_RUNNER:
        return _execute_default_selected_tests(
            selected_tests, runner_args=runner_args, root=root
        )
    command = [*runner, *selected_tests, *runner_args]
    completed = subprocess.run(command, cwd=root or project_root(), check=False)
    return completed.returncode


def run_changed_test_workflow(request: TestSelectionRequest) -> int:
    """Run or list tests selected by the changed-test workflow."""

    changed_files = request.files
    if not changed_files:
        changed_files = changed_files_since(request.since_ref or DEFAULT_SINCE_REF)
    result = select_tests_for_changed_files(changed_files)
    if request.list_only:
        for test_path in result.selected_tests:
            print(test_path)
        return 0
    if not result.selected_tests:
        print("No impacted tests selected.")
        return 0
    return execute_selected_tests(
        result.selected_tests,
        runner=request.runner,
        runner_args=request.runner_args,
    )


def _test_tokens_match_changed_source(
    tokens: set[str], symbols: Sequence[ProductionSymbol], modules: set[str]
) -> bool:
    return any(symbol_is_referenced(symbol, tokens) for symbol in symbols) or bool(
        modules & tokens
    )


def _execute_default_selected_tests(
    selected_tests: Sequence[str],
    *,
    runner_args: Sequence[str],
    root: Path | None = None,
) -> int:
    cwd = root or project_root()
    js_ts_tests = tuple(path for path in selected_tests if is_js_ts_test_path(path))
    python_tests = tuple(path for path in selected_tests if path not in js_ts_tests)
    if python_tests:
        completed = subprocess.run(
            [*DEFAULT_TEST_RUNNER, *python_tests, *runner_args], cwd=cwd, check=False
        )
        if completed.returncode != 0:
            return completed.returncode
    if js_ts_tests:
        return execute_default_js_ts_tests(
            js_ts_tests, runner_args=runner_args, root=cwd
        )
    return 0
