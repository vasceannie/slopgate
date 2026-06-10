from __future__ import annotations
import json
import subprocess
from pathlib import Path
from typing import cast
from hypothesis import given
from hypothesis import strategies
from slopgate._types import object_list
from slopgate.cli.lint import lint_check, lint_freeze
from slopgate.lint._baseline import Violation, compute_synced_baseline_rules
from tests.lint_paths_support import (
    freeze_rules_payload,
    seed_freeze_repo,
    write_slopgate_toml,
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _commit(repo: Path, message: str) -> None:
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=Slopgate Tests",
            "-c",
            "user.email=slopgate-tests@example.invalid",
            "commit",
            "-m",
            message,
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _seed_git_base_debt_repo(tmp_path: Path) -> Path:
    write_slopgate_toml(tmp_path, '[paths]\nsrc = "src"\n')
    src = tmp_path / "src"
    src.mkdir()
    (src / "base_debt.py").write_text("x = 1\n" * 130, encoding="utf-8")
    _git(tmp_path, "init", "-b", "main")
    _git(tmp_path, "add", "slopgate.toml", "src/base_debt.py")
    _commit(tmp_path, "seed base debt")
    _git(tmp_path, "checkout", "-b", "feature")
    return src


def _recorded_rule_ids(tmp_path: Path) -> list[str]:
    rules_obj = freeze_rules_payload(tmp_path)["rules"]
    assert isinstance(rules_obj, dict)
    rules = cast(dict[object, object], rules_obj)
    recorded: list[str] = []
    for ids_obj in rules.values():
        if isinstance(ids_obj, list):
            recorded.extend(
                (
                    item
                    for item in object_list(cast(object, ids_obj))
                    if isinstance(item, str)
                )
            )
    return recorded


def _seed_empty_baseline_repo(tmp_path: Path) -> Path:
    write_slopgate_toml(tmp_path, '[paths]\nsrc = "src"\n')
    src = tmp_path / "src"
    src.mkdir()
    (src / "clean.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "baselines.json").write_text(
        json.dumps({"schema_version": 1, "rules": {}}), encoding="utf-8"
    )
    assert lint_freeze(tmp_path) == 0
    return src


def _baseline_rule_value(tmp_path: Path, rule_name: str) -> object:
    rules_obj = freeze_rules_payload(tmp_path)["rules"]
    assert isinstance(rules_obj, dict)
    return cast(dict[object, object], rules_obj).get(rule_name)


def test_compute_synced_prune_only_drops_stale_ids() -> None:
    collectors = [
        (
            "demo-rule",
            [Violation(rule="demo-rule", relative_path="a.py", identifier="keep")],
        )
    ]
    old = {"demo-rule": {"demo-rule|a.py|keep", "demo-rule|a.py|stale"}}
    synced, removed = compute_synced_baseline_rules(collectors, old, prune_only=True)
    assert removed == 1
    assert synced == {"demo-rule": {"demo-rule|a.py|keep"}}


def test_compute_synced_full_mirror_includes_current() -> None:
    collectors = [
        (
            "demo-rule",
            [Violation(rule="demo-rule", relative_path="b.py", identifier="new-hit")],
        )
    ]
    synced, removed = compute_synced_baseline_rules(collectors, {}, prune_only=False)
    assert removed == 0
    assert synced == {"demo-rule": {"demo-rule|b.py|new-hit"}}


_ID_SETS = strategies.sets(
    strategies.text(alphabet="abc", min_size=1, max_size=4), max_size=6
)


@given(old_ids=_ID_SETS, current_ids=_ID_SETS, accepted_ids=_ID_SETS)
def test_compute_synced_prune_only_keeps_only_current_accepted_debt(
    old_ids: set[str], current_ids: set[str], accepted_ids: set[str]
) -> None:

    def stable_id(identifier: str) -> str:
        return f"demo-rule|demo.py|{identifier}"

    collectors = [
        (
            "demo-rule",
            [
                Violation("demo-rule", "demo.py", identifier)
                for identifier in sorted(current_ids)
            ],
        )
    ]
    old = {"demo-rule": {stable_id(item) for item in old_ids}}
    accepted = {"demo-rule": {stable_id(item) for item in accepted_ids}}
    synced, removed = compute_synced_baseline_rules(
        collectors, old, prune_only=True, accepted_baseline=accepted
    )
    expected = {stable_id(item) for item in (old_ids | accepted_ids) & current_ids}
    assert removed == len(old["demo-rule"] - {stable_id(item) for item in current_ids})
    assert synced == ({"demo-rule": expected} if expected else {})


def test_lint_check_prunes_fixed_debt_from_baseline(tmp_path: Path) -> None:
    seed_freeze_repo(tmp_path)
    assert lint_freeze(tmp_path) == 0
    before = freeze_rules_payload(tmp_path)["rules"]
    assert isinstance(before, dict) and before
    wide = tmp_path / "src" / "wide.py"
    wide.write_text("x = 1\n", encoding="utf-8")
    assert lint_check(tmp_path) == 0
    after = freeze_rules_payload(tmp_path)["rules"]
    assert after == {}


def test_lint_check_does_not_add_new_violations_while_pruning(tmp_path: Path) -> None:
    src = _seed_empty_baseline_repo(tmp_path)
    (src / "wide.py").write_text("x = 1\n" * 130, encoding="utf-8")
    assert lint_check(tmp_path) == 1
    assert not _baseline_rule_value(tmp_path, "long-method")


def test_lint_check_treats_git_base_findings_as_inherited_debt(tmp_path: Path) -> None:
    _seed_git_base_debt_repo(tmp_path)
    assert lint_check(tmp_path) == 0
    recorded_ids = _recorded_rule_ids(tmp_path)
    assert any(("src/base_debt.py" in item for item in recorded_ids))


def test_lint_check_persists_only_git_base_debt_when_branch_adds_new_finding(
    tmp_path: Path,
) -> None:
    src = _seed_git_base_debt_repo(tmp_path)
    (src / "branch_debt.py").write_text("x = 1\n" * 130, encoding="utf-8")
    assert lint_check(tmp_path) == 1
    recorded_ids = _recorded_rule_ids(tmp_path)
    assert any(("src/base_debt.py" in item for item in recorded_ids))
    assert not any(("src/branch_debt.py" in item for item in recorded_ids))
