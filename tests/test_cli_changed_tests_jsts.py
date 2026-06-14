"""JS/TS changed-test selector coverage for the ``slopgate test`` workflow."""

from __future__ import annotations

import subprocess
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch

import pytest
from hypothesis import given

from slopgate.cli import changed_tests
from slopgate.cli import js_ts_tests
from slopgate.cli.changed_tests import DEFAULT_TEST_RUNNER, changed_files_since
from tests.cli_changed_tests_jsts_support import (
    JS_TS_STEM_TEXT,
    JS_TS_SUFFIX,
    prepare_js_ts_project,
    run_js_ts_executor_property_case,
)


def test_selector_returns_nested_js_ts_sibling_tests(
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare_js_ts_project(tmp_project, monkeypatch)

    result = changed_tests.select_tests_for_changed_files(
        ("apps/web/src/components/Button.tsx", "apps/web/src/components/Card.ts")
    )

    assert result.selected_tests == (
        "apps/web/src/components/Button.test.tsx",
        "apps/web/src/components/Card.spec.ts",
    ), "nested JS/TS sources should select sibling test/spec files"


def test_js_ts_path_helpers_classify_sources_and_tests() -> None:
    assert js_ts_tests.is_js_ts_path("apps/web/src/Button.tsx"), (
        "TSX source files should be classified as JS/TS paths"
    )
    assert not js_ts_tests.is_js_ts_path("src/pkg/core.py"), (
        "Python files should not be classified as JS/TS paths"
    )
    assert js_ts_tests.is_js_ts_test_path("apps/web/src/Button.spec.tsx"), (
        "JS/TS spec files should be classified as JS/TS tests"
    )
    assert not js_ts_tests.is_js_ts_test_path("apps/web/src/Button.tsx"), (
        "JS/TS source files should not be classified as tests"
    )


def test_select_js_ts_tests_returns_nested_sibling_tests(
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare_js_ts_project(tmp_project, monkeypatch)

    selected = js_ts_tests.select_js_ts_tests(
        ("apps/web/src/components/Button.tsx",), root=tmp_project
    )

    assert selected == ("apps/web/src/components/Button.test.tsx",), (
        "JS/TS helper should select sibling tests directly"
    )


@given(stem=JS_TS_STEM_TEXT, suffix=JS_TS_SUFFIX)
def test_select_js_ts_tests_selects_sibling_test_property(
    stem: str, suffix: str
) -> None:
    with TemporaryDirectory() as raw_root:
        root = Path(raw_root)
        source_root = root / "src"
        source_root.mkdir()
        source = source_root / f"{stem}{suffix}"
        test = source_root / f"{stem}.test{suffix}"
        source.write_text("export const value = 1\n", encoding="utf-8")
        test.write_text("test('value', () => {})\n", encoding="utf-8")

        selected = js_ts_tests.select_js_ts_tests((f"src/{stem}{suffix}",), root=root)

    assert selected == (f"src/{stem}.test{suffix}",), (
        "JS/TS selector should preserve sibling source-to-test naming invariants"
    )


def test_select_js_ts_tests_matches_extended_test_marker_names() -> None:
    with TemporaryDirectory() as raw_root:
        root = Path(raw_root)
        source_root = root / "src" / "components"
        source_root.mkdir(parents=True)
        (source_root / "Button.tsx").write_text(
            "export const Button = () => null\n", encoding="utf-8"
        )
        (source_root / "Button.test.integration.tsx").write_text(
            "test('button', () => {})\n", encoding="utf-8"
        )

        selected = js_ts_tests.select_js_ts_tests(
            ("src/components/Button.tsx",), root=root
        )

    assert selected == ("src/components/Button.test.integration.tsx",), (
        "JS/TS selector should honor the documented *.test.* naming pattern"
    )


def test_selector_returns_changed_js_ts_test_file(
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare_js_ts_project(tmp_project, monkeypatch)

    result = changed_tests.select_tests_for_changed_files(
        ("apps/web/src/components/Button.test.tsx",)
    )

    assert result.selected_tests == ("apps/web/src/components/Button.test.tsx",), (
        "changed JS/TS test files should select themselves"
    )


def test_default_runner_executes_js_ts_tests_with_nearest_package_json(
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare_js_ts_project(tmp_project, monkeypatch)
    observed_command: list[str] = []
    observed_cwd: list[Path] = []

    def record_npm_test(
        command: list[str], *, cwd: Path, check: bool
    ) -> subprocess.CompletedProcess[str]:
        assert check is False, "JS/TS npm runner should not raise on failures"
        observed_command.extend(command)
        observed_cwd.append(cwd)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(js_ts_tests.subprocess, "run", record_npm_test)
    request = changed_tests.TestSelectionRequest(
        since_ref=None,
        files=("apps/web/src/components/Button.tsx",),
        list_only=False,
        smoke=False,
        runner=DEFAULT_TEST_RUNNER,
        runner_args=("--watch=false",),
    )

    result = changed_tests.run_changed_test_workflow(request)

    assert result == 0, "default runner should execute selected JS/TS tests"
    assert observed_command == [
        "npm",
        "test",
        "--",
        "src/components/Button.test.tsx",
        "--watch=false",
    ], "JS/TS default execution should use npm test with package-relative test paths"
    assert observed_cwd == [tmp_project / "apps" / "web"], (
        "JS/TS default execution should run from the nearest package.json directory"
    )


def test_execute_default_js_ts_tests_runs_nearest_package_json(
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prepare_js_ts_project(tmp_project, monkeypatch)
    observed_command: list[str] = []

    def record_npm_test(
        command: list[str], *, cwd: Path, check: bool
    ) -> subprocess.CompletedProcess[str]:
        assert cwd == tmp_project / "apps" / "web", "npm should run near package.json"
        assert check is False, "npm command should return its exit code"
        observed_command.extend(command)
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(js_ts_tests.subprocess, "run", record_npm_test)

    result = js_ts_tests.execute_default_js_ts_tests(
        ("apps/web/src/components/Button.test.tsx",), root=tmp_project
    )

    assert result == 0, "JS/TS default executor should return npm's exit code"
    assert observed_command == [
        "npm",
        "test",
        "--",
        "src/components/Button.test.tsx",
    ], "JS/TS default executor should pass package-relative test paths"


@given(stem=JS_TS_STEM_TEXT, suffix=JS_TS_SUFFIX)
def test_execute_default_js_ts_tests_passes_package_relative_paths_property(
    stem: str, suffix: str
) -> None:
    result, observed_command = run_js_ts_executor_property_case(stem, suffix)

    assert result == 0, "JS/TS executor should propagate a successful npm exit"
    assert observed_command == ("npm", "test", "--", f"src/{stem}.test{suffix}"), (
        "JS/TS executor should pass package-relative test paths for any safe stem"
    )


def test_changed_files_since_includes_submodule_head_changes(
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    submodule_root = tmp_project / "vendor" / "widget"

    def changed_file_git(
        command: list[str], *, cwd: Path, **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        if command[:3] == ["git", "submodule", "status"]:
            return subprocess.CompletedProcess(
                command, 0, stdout=" abc123 vendor/widget (heads/main)\n", stderr=""
            )
        if cwd == tmp_project:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(
            command, 0, stdout="src/components/Widget.tsx\n", stderr=""
        )

    monkeypatch.setattr(changed_tests.subprocess, "run", changed_file_git)

    changed = changed_files_since("HEAD", root=tmp_project)
    submodule_changed = js_ts_tests.changed_files_in_submodules(tmp_project, "HEAD")

    assert changed == ("vendor/widget/src/components/Widget.tsx",), (
        "default changed-file discovery should include nested submodule worktree paths"
    )
    assert submodule_changed == ("vendor/widget/src/components/Widget.tsx",), (
        "submodule helper should prefix nested changed paths with submodule path"
    )
    assert submodule_root.relative_to(tmp_project).as_posix() == "vendor/widget", (
        "test setup should model a nested submodule path"
    )


def test_changed_files_since_expands_parent_submodule_gitlink_changes(
    tmp_project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def changed_file_git(
        command: list[str], *, cwd: Path, **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        if command[:3] == ["git", "submodule", "status"]:
            return subprocess.CompletedProcess(
                command, 0, stdout=" newsha vendor/widget (heads/main)\n", stderr=""
            )
        if command[:3] == ["git", "ls-tree", "HEAD"]:
            return subprocess.CompletedProcess(
                command, 0, stdout="160000 commit oldsha\tvendor/widget\n", stderr=""
            )
        if command[:2] == ["git", "rev-parse"]:
            return subprocess.CompletedProcess(command, 0, stdout="newsha\n", stderr="")
        if cwd == tmp_project:
            return subprocess.CompletedProcess(
                command, 0, stdout="vendor/widget\n", stderr=""
            )
        return subprocess.CompletedProcess(
            command, 0, stdout="src/components/Widget.tsx\n", stderr=""
        )

    monkeypatch.setattr(changed_tests.subprocess, "run", changed_file_git)

    changed = changed_files_since("HEAD", root=tmp_project)
    submodule_changed = js_ts_tests.changed_files_in_submodules(tmp_project, "HEAD")

    assert changed == (
        "vendor/widget",
        "vendor/widget/src/components/Widget.tsx",
    ), "parent gitlink changes should include expanded nested submodule file paths"
    assert submodule_changed == ("vendor/widget/src/components/Widget.tsx",), (
        "submodule helper should diff parent-recorded gitlink SHA against HEAD"
    )


@given(stem=JS_TS_STEM_TEXT, suffix=JS_TS_SUFFIX)
def test_changed_files_in_submodules_prefixes_nested_paths_property(
    stem: str, suffix: str
) -> None:
    nested_path = f"src/components/{stem}{suffix}"

    def submodule_git(
        command: list[str], **_kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        if command[:3] == ["git", "submodule", "status"]:
            return subprocess.CompletedProcess(
                command, 0, stdout=" abc123 vendor/widget (heads/main)\n", stderr=""
            )
        return subprocess.CompletedProcess(
            command, 0, stdout=f"{nested_path}\n", stderr=""
        )

    with TemporaryDirectory() as raw_root:
        root = Path(raw_root)
        with patch.object(js_ts_tests.subprocess, "run", side_effect=submodule_git):
            changed = js_ts_tests.changed_files_in_submodules(root, "HEAD")

    assert changed == (f"vendor/widget/{nested_path}",), (
        "submodule changed paths should be returned relative to the parent repo"
    )
