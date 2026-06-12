from __future__ import annotations

import importlib
from collections.abc import Callable
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Protocol, cast

from hypothesis import given, strategies

LOWER_IDENTIFIER = strategies.from_regex("[a-z][a-z0-9_]{0,10}", fullmatch=True)
SHORT_TEXT = strategies.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789 _.-/", max_size=40
)


class _ConfiguredLintFiles(Protocol):
    def __call__(self, root: Path, *, force_all_scope: bool) -> object: ...


class _GitBaseDebtModule(Protocol):
    def scan_git_base_debt(
        self, project_root: Path, *, configured_lint_files: _ConfiguredLintFiles
    ) -> object | None: ...


class _LintFilesFactory(Protocol):
    def __call__(
        self, *, cfg: object, src_files: list[Path], test_files: list[Path]
    ) -> object: ...


class _ReportModule(Protocol):
    LintFiles: _LintFilesFactory


class _ReportFormatModule(Protocol):
    def existing_location_lines(
        self, violation: object, *, color: bool
    ) -> list[str]: ...


class _ViolationFactory(Protocol):
    def __call__(
        self,
        rule_name: str,
        path: str,
        signature: str,
        *,
        metadata: dict[str, object],
    ) -> object: ...


class _LintModule(Protocol):
    Violation: _ViolationFactory


class _ConfigModule(Protocol):
    def load_config(self, project_root: Path) -> object: ...


_error_output_signals = importlib.import_module("slopgate.rules._error_output_signals")
has_error_signals: Callable[[str], bool] = getattr(
    _error_output_signals, "has_error_signals"
)
_git_base_debt = cast(
    _GitBaseDebtModule, importlib.import_module("slopgate.cli.lint.git_base_debt")
)
_report = cast(_ReportModule, importlib.import_module("slopgate.cli.lint.report"))
_report_format = cast(
    _ReportFormatModule, importlib.import_module("slopgate.cli.lint.report_format")
)
_lint = cast(_LintModule, importlib.import_module("slopgate.lint"))
_config = cast(_ConfigModule, importlib.import_module("slopgate.lint._config"))


def _configured_lint_files(root: Path, *, force_all_scope: bool) -> object:
    if not force_all_scope:
        raise AssertionError("git-base debt scan should request all files")
    return _report.LintFiles(
        cfg=_config.load_config(root),
        src_files=[root / "src" / "sample.py"],
        test_files=[],
    )


@given(locations=strategies.lists(SHORT_TEXT.filter(bool), min_size=1, max_size=4))
def test_existing_location_lines_renders_string_locations_property(
    locations: list[str],
) -> None:
    violation = _lint.Violation(
        "manual-rule",
        "src/example.py",
        "identifier",
        metadata={"existing_locations": locations, "existing_locations_more": 1},
    )

    lines = _report_format.existing_location_lines(violation, color=False)

    assert {
        "count": len(lines),
        "locations": all(item in lines[0] for item in locations),
    } == {
        "count": 1,
        "locations": True,
    }
    assert "+1 more" in lines[0]


@given(noise=SHORT_TEXT)
def test_has_error_signals_detects_traceback_with_exception_property(
    noise: str,
) -> None:
    output = f"{noise}\nTraceback (most recent call last)\nRuntimeError: failed\n"

    assert {
        "classified": has_error_signals(output),
        "contains_error": "RuntimeError: failed" in output,
    } == {"classified": True, "contains_error": True}


@given(project_name=LOWER_IDENTIFIER)
def test_scan_git_base_debt_returns_none_outside_git_repo_property(
    project_name: str,
) -> None:
    configured: _ConfiguredLintFiles = _configured_lint_files
    with TemporaryDirectory() as raw_path:
        root = Path(raw_path) / project_name
        root.mkdir()

        debt = _git_base_debt.scan_git_base_debt(root, configured_lint_files=configured)

    assert debt is None
