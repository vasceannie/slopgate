from __future__ import annotations

from pathlib import Path

import pytest

from slopgate.lint._collector_groups.runners import run_touched_collectors
from slopgate.lint._config import load_config, set_config
from slopgate.rules.projected_lint.collectors import (
    PROJECTED_COLLECTOR_SCOPES,
    collect_projected_lint_report,
)


@pytest.mark.parametrize(
    ("relative_path", "content", "expected_collector"),
    [
        ("src/broken.py", "def broken(:\n", "python-parse-error"),
        (
            "src/long_method.py",
            "def calculate() -> int:\n    value = 0\n"
            + ("    value += 1\n" * 90)
            + "    return value\n",
            "long-method",
        ),
        (
            "tests/test_branch.py",
            "def test_branch(flag: bool) -> None:\n    if flag:\n        assert True\n",
            "conditional-assertion",
        ),
    ],
    ids=("parse", "code-smell", "test-smell"),
)
def test_projected_touched_collectors_cover_deterministic_file_rules(
    projected_repo: Path,
    relative_path: str,
    content: str,
    expected_collector: str,
) -> None:
    failing = _failing_collectors(projected_repo, relative_path, content)
    assert expected_collector in failing, (
        f"Projected lint should run {expected_collector}, got {sorted(failing)}"
    )


def _failing_collectors(repo: Path, relative_path: str, content: str) -> set[str]:
    target = repo / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    set_config(load_config(repo))
    is_test = relative_path.startswith("tests/")
    results = run_touched_collectors(
        [] if is_test else [target],
        [target] if is_test else [],
        deterministic_file_only=True,
    )
    return {name for name, violations in results if violations}


def test_projected_collector_scope_excludes_project_and_suite_checks() -> None:
    assert PROJECTED_COLLECTOR_SCOPES == frozenset({"file", "touched"}), (
        "Projected lint should remain deterministic and touched-file scoped"
    )


def test_projected_lint_report_routes_src_and_test_files(projected_repo: Path) -> None:
    src_file = projected_repo / "src/broken.py"
    test_file = projected_repo / "tests/test_branch.py"
    src_file.write_text("def broken(:\n", encoding="utf-8")
    test_file.parent.mkdir(parents=True, exist_ok=True)
    test_file.write_text(
        "def test_branch(flag: bool) -> None:\n    if flag:\n        assert True\n",
        encoding="utf-8",
    )

    report = collect_projected_lint_report(projected_repo, (src_file, test_file))

    assert report.failures == ["python-parse-error: 1", "conditional-assertion: 1"], (
        "Projected report should route src and pytest files to their collectors"
    )


def test_projected_runner_skips_project_indexes(
    projected_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = projected_repo / "src/app.py"
    set_config(load_config(projected_repo))

    def fail_project_index(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("project index must not run")

    monkeypatch.setattr(
        "slopgate.lint.project_index.build_project_index", fail_project_index
    )
    monkeypatch.setattr(
        "slopgate.quality.constant_index.build_project_constant_index",
        fail_project_index,
    )

    results = run_touched_collectors([target], [], deterministic_file_only=True)

    assert isinstance(results, list), "Projected collector run should complete"
