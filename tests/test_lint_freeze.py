from __future__ import annotations

import json
from pathlib import Path

from slopgate.cli.lint import _lint_freeze
from tests.lint_paths_support import freeze_rules_payload, seed_freeze_repo, write_slopgate_toml


def test_lint_freeze_writes_current_findings(tmp_path: Path) -> None:
    seed_freeze_repo(tmp_path)

    assert _lint_freeze(tmp_path) == 0

    rules = freeze_rules_payload(tmp_path)["rules"]
    assert isinstance(rules, dict) and rules and any(ids for ids in rules.values())


def test_lint_freeze_refuses_when_baseline_already_populated(tmp_path: Path) -> None:
    write_slopgate_toml(tmp_path, '[paths]\nsrc = "src"\n')
    (tmp_path / "baselines.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "rules": {"long-method": ["src/a.py:fn"]},
            }
        ),
        encoding="utf-8",
    )

    assert _lint_freeze(tmp_path) == 1
