from __future__ import annotations

import json
from pathlib import Path

from slopgate.cli.lint import _lint_check, _lint_freeze
from slopgate.lint._baseline import Violation, compute_synced_baseline_rules
from tests.lint_paths_support import freeze_rules_payload, seed_freeze_repo, write_slopgate_toml


def test_compute_synced_prune_only_drops_stale_ids() -> None:
    collectors = [
        (
            "demo-rule",
            [
                Violation(
                    rule="demo-rule",
                    relative_path="a.py",
                    identifier="keep",
                )
            ],
        )
    ]
    old = {
        "demo-rule": {
            "demo-rule|a.py|keep",
            "demo-rule|a.py|stale",
        }
    }
    synced, removed = compute_synced_baseline_rules(
        collectors,
        old,
        prune_only=True,
    )
    assert removed == 1
    assert synced == {"demo-rule": {"demo-rule|a.py|keep"}}


def test_compute_synced_full_mirror_includes_current() -> None:
    collectors = [
        (
            "demo-rule",
            [
                Violation(
                    rule="demo-rule",
                    relative_path="b.py",
                    identifier="new-hit",
                )
            ],
        )
    ]
    synced, removed = compute_synced_baseline_rules(
        collectors,
        {},
        prune_only=False,
    )
    assert removed == 0
    assert synced == {"demo-rule": {"demo-rule|b.py|new-hit"}}


def test_lint_check_prunes_fixed_debt_from_baseline(tmp_path: Path) -> None:
    seed_freeze_repo(tmp_path)
    assert _lint_freeze(tmp_path) == 0
    before = freeze_rules_payload(tmp_path)["rules"]
    assert isinstance(before, dict) and before

    wide = tmp_path / "src" / "wide.py"
    wide.write_text("x = 1\n", encoding="utf-8")

    assert _lint_check(tmp_path) == 0
    after = freeze_rules_payload(tmp_path)["rules"]
    assert after == {}


def test_lint_check_does_not_add_new_violations_while_pruning(tmp_path: Path) -> None:
    write_slopgate_toml(tmp_path, '[paths]\nsrc = "src"\n')
    src = tmp_path / "src"
    src.mkdir()
    (src / "clean.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "baselines.json").write_text(
        json.dumps({"schema_version": 1, "rules": {}}),
        encoding="utf-8",
    )
    assert _lint_freeze(tmp_path) == 0
    (src / "wide.py").write_text("x = 1\n" * 130, encoding="utf-8")

    assert _lint_check(tmp_path) == 1
    rules = freeze_rules_payload(tmp_path)["rules"]
    assert isinstance(rules, dict)
    assert "long-method" not in rules or not rules.get("long-method")
