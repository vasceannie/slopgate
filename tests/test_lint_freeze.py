from __future__ import annotations

import json
from pathlib import Path

import pytest

from slopgate.cli.lint import _lint_freeze
from slopgate.lint._config import reset_config


@pytest.fixture(autouse=True)
def _reset_lint_config() -> None:
    yield
    reset_config()


def test_lint_freeze_writes_current_findings(tmp_path: Path) -> None:
    src = tmp_path / "src"
    _ = src.mkdir()
    _ = (src / "wide.py").write_text("x = 1\n" * 130, encoding="utf-8")
    _ = (tmp_path / "slopgate.toml").write_text('[paths]\nsrc = "src"\n', encoding="utf-8")
    _ = (tmp_path / "baselines.json").write_text(
        '{"schema_version": 1, "rules": {}}\n',
        encoding="utf-8",
    )

    assert _lint_freeze(tmp_path) == 0

    payload = json.loads((tmp_path / "baselines.json").read_text(encoding="utf-8"))
    rules = payload["rules"]
    assert isinstance(rules, dict)
    assert rules
    assert any(ids for ids in rules.values())


def test_lint_freeze_refuses_when_baseline_already_populated(tmp_path: Path) -> None:
    _ = (tmp_path / "slopgate.toml").write_text("[paths]\nsrc = \"src\"\n", encoding="utf-8")
    _ = (tmp_path / "baselines.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "rules": {"long-method": ["src/a.py:fn"]},
            }
        ),
        encoding="utf-8",
    )

    assert _lint_freeze(tmp_path) == 1
