"""Deterministic touched-file collector execution for projected overlays."""

from __future__ import annotations

from pathlib import Path

from slopgate.constants import PYTEST_TEST_PREFIX
from slopgate.rules.common.quality.lint import (
    TouchedLintReport,
    collect_lint_report_for_files,
)

PROJECTED_COLLECTOR_SCOPES = frozenset({"file", "touched"})


def collect_projected_lint_report(
    overlay_root: Path, files: tuple[Path, ...]
) -> TouchedLintReport:
    src_files: list[Path] = []
    test_files: list[Path] = []
    for path in files:
        relative = path.relative_to(overlay_root).as_posix()
        if relative.startswith("tests/") or path.name.startswith(PYTEST_TEST_PREFIX):
            test_files.append(path)
        else:
            src_files.append(path)
    return collect_lint_report_for_files(
        src_files,
        test_files,
        config_root=overlay_root,
        deterministic_file_only=True,
    )


__all__ = ["PROJECTED_COLLECTOR_SCOPES", "collect_projected_lint_report"]
