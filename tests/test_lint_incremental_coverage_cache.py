from __future__ import annotations

import json
from pathlib import Path

import pytest

from slopgate.lint._baseline import Violation
from slopgate.lint._collectors import CollectorRunOptions, run_all_collectors
from slopgate.lint._config import load_config, reset_config, set_config


def _configure_root(root: Path) -> None:
    (root / "slopgate.toml").write_text(
        "[slopgate]\nenabled = true\n", encoding="utf-8"
    )
    set_config(load_config(root))


def _write_source(root: Path) -> Path:
    source = root / "src/pkg/app.py"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("def answer() -> int:\n    return 1\n", encoding="utf-8")
    return source


def _write_coverage(root: Path, artifact_name: str, percent: int) -> Path:
    artifact = root / artifact_name
    if artifact.suffix == ".json":
        content = json.dumps(
            {
                "files": {
                    "src/pkg/app.py": {"summary": {"percent_covered": percent}}
                }
            }
        )
    else:
        content = (
            "<coverage><packages><package><classes>"
            f'<class filename="src/pkg/app.py" line-rate="{percent / 100}" />'
            "</classes></package></packages></coverage>"
        )
    artifact.write_text(content, encoding="utf-8")
    return artifact


def _coverage_findings(
    root: Path, source: Path, *, use_index: bool = True
) -> list[Violation]:
    return dict(
        run_all_collectors(
            [source],
            [],
            CollectorRunOptions(persist_index=use_index, use_index=use_index),
        )
    )["untested-production-code"]


def _creation_contract(root: Path, artifact_name: str) -> tuple[str, int, bool]:
    _configure_root(root)
    source = _write_source(root)
    initial = _coverage_findings(root, source)
    _write_coverage(root, artifact_name, 100)
    updated = _coverage_findings(root, source)
    reference = _coverage_findings(root, source, use_index=False)
    reset_config()
    return str(initial[0].metadata["coverage_kind"]), len(updated), updated == reference


def _change_contract(root: Path, artifact_name: str) -> tuple[str, str, bool]:
    _configure_root(root)
    source = _write_source(root)
    _write_coverage(root, artifact_name, 100)
    _coverage_findings(root, source)
    _write_coverage(root, artifact_name, 0)
    updated = _coverage_findings(root, source)
    reference = _coverage_findings(root, source, use_index=False)
    reset_config()
    return (
        str(updated[0].metadata["coverage_percent"]),
        str(updated[0].metadata["coverage_source"]),
        updated == reference,
    )


def _removal_contract(root: Path, artifact_name: str) -> tuple[int, str, bool]:
    _configure_root(root)
    source = _write_source(root)
    artifact = _write_coverage(root, artifact_name, 100)
    initial = _coverage_findings(root, source)
    artifact.unlink()
    updated = _coverage_findings(root, source)
    reference = _coverage_findings(root, source, use_index=False)
    reset_config()
    return len(initial), str(updated[0].metadata["coverage_kind"]), updated == reference


@pytest.mark.parametrize("artifact_name", ("coverage.json", "coverage.xml"))
def test_coverage_artifact_creation_invalidates_clean_cache(
    tmp_path: Path, artifact_name: str
) -> None:
    assert _creation_contract(tmp_path, artifact_name) == (
        "static-reference",
        0,
        True,
    )


@pytest.mark.parametrize("artifact_name", ("coverage.json", "coverage.xml"))
def test_coverage_artifact_change_invalidates_clean_cache(
    tmp_path: Path, artifact_name: str
) -> None:
    assert _change_contract(tmp_path, artifact_name) == ("0", artifact_name, True)


@pytest.mark.parametrize("artifact_name", ("coverage.json", "coverage.xml"))
def test_coverage_artifact_removal_invalidates_clean_cache(
    tmp_path: Path, artifact_name: str
) -> None:
    assert _removal_contract(tmp_path, artifact_name) == (0, "static-reference", True)
