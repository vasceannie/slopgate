from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

import pytest
from slopgate.cli import repair
from slopgate.lint._baseline import Violation


class _Store:
    def __call__(self, _cwd: str) -> _Store:
        return self

    def get_repair_required(self) -> dict[str, object]:
        return {
            "generation": "generation-one",
            "rule_ids": ["QUALITY-LINT-001"],
            "paths": ["src/app.py"],
        }

    def clear_repair_required(self, _generation: str) -> bool:
        return True


class _CollectorCapture:
    def __init__(self) -> None:
        self.files: list[tuple[tuple[Path, ...], tuple[Path, ...]]] = []

    def __call__(
        self,
        src_files: list[Path],
        test_files: list[Path],
        *_args: object,
        **_kwargs: object,
    ) -> list[tuple[str, list[Violation]]]:
        self.files.append((tuple(src_files), tuple(test_files)))
        return []


def test_repair_verify_passes_only_recorded_paths_to_collectors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorded = tmp_path / "src" / "app.py"
    store = _Store()
    collector = _CollectorCapture()

    def resolve(
        _cwd: Path, _paths: Sequence[str]
    ) -> tuple[list[Path], list[Path], list[str]]:
        return [recorded], [], []

    monkeypatch.setattr("slopgate.cli.repair._store", store)
    monkeypatch.setattr("slopgate.cli.repair._resolve_repair_files", resolve)
    monkeypatch.setattr("slopgate.lint._collectors.run_all_collectors", collector)
    result = repair.cmd_repair_verify(
        argparse.Namespace(cwd=str(tmp_path), generation="generation-one")
    )

    assert result == 0, "clean recorded paths should complete repair verification"
    assert collector.files == [((recorded,), ())], (
        "repair verification must not send unrelated project files to collectors"
    )
