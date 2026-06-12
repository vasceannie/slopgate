from __future__ import annotations
import json
import subprocess
from pathlib import Path
from typing import cast
from hypothesis import given
from hypothesis import strategies
import slopgate.lint._baseline
from slopgate._types import object_dict, object_list
from slopgate.cli.lint import lint_check, lint_freeze
from tests.lint_paths_support import (
    freeze_rules_payload,
    seed_freeze_repo,
    write_slopgate_toml,
)

GIT_TEST_USER_NAME = "Slopgate Tests"
GIT_TEST_USER_EMAIL = "slopgate-tests@example.invalid"


def _run_git(repo: Path, *args: str, test_identity: bool = False) -> None:
    command = ["git", "-C", str(repo)]
    if test_identity:
        command.extend(
            [
                "-c",
                f"user.name={GIT_TEST_USER_NAME}",
                "-c",
                f"user.email={GIT_TEST_USER_EMAIL}",
            ]
        )
    command.extend(args)
    subprocess.run(
        command,
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
    _run_git(tmp_path, "init", "-b", "main")
    _run_git(tmp_path, "add", "slopgate.toml", "src/base_debt.py")
    _run_git(tmp_path, "commit", "-m", "seed base debt", test_identity=True)
    _run_git(tmp_path, "checkout", "-b", "feature")
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


def _single_git_base_cache_file(tmp_path: Path) -> Path:
    cache_files = sorted((tmp_path / ".slopgate/cache/git-base-debt").glob("*.json"))
    assert len(cache_files) == 1, "Expected one git-base debt cache entry"
    return cache_files[0]


def _cached_git_base_rule_ids(tmp_path: Path) -> list[str]:
    cache_file = _single_git_base_cache_file(tmp_path)
    cache_payload = object_dict(json.loads(cache_file.read_text(encoding="utf-8")))
    rules = object_dict(cache_payload.get("rules"))
    return [
        item
        for ids in rules.values()
        for item in object_list(ids)
        if isinstance(item, str)
    ]


def test_compute_synced_prune_only_drops_stale_ids() -> None:
    collectors = [
        (
            "demo-rule",
            [
                slopgate.lint._baseline.Violation(
                    rule="demo-rule", relative_path="a.py", identifier="keep"
                )
            ],
        )
    ]
    old = {"demo-rule": {"demo-rule|a.py|keep", "demo-rule|a.py|stale"}}
    synced, removed = slopgate.lint._baseline.compute_synced_baseline_rules(
        collectors, old, prune_only=True
    )
    assert removed == 1
    assert synced == {"demo-rule": {"demo-rule|a.py|keep"}}


def test_compute_synced_full_mirror_includes_current() -> None:
    collectors = [
        (
            "demo-rule",
            [
                slopgate.lint._baseline.Violation(
                    rule="demo-rule", relative_path="b.py", identifier="new-hit"
                )
            ],
        )
    ]
    synced, removed = slopgate.lint._baseline.compute_synced_baseline_rules(
        collectors, {}, prune_only=False
    )
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
                slopgate.lint._baseline.Violation("demo-rule", "demo.py", identifier)
                for identifier in sorted(current_ids)
            ],
        )
    ]
    old = {"demo-rule": {stable_id(item) for item in old_ids}}
    accepted = {"demo-rule": {stable_id(item) for item in accepted_ids}}
    synced, removed = slopgate.lint._baseline.compute_synced_baseline_rules(
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


def test_lint_check_writes_git_base_debt_cache_for_repeated_checks(
    tmp_path: Path,
) -> None:
    _seed_git_base_debt_repo(tmp_path)
    assert lint_check(tmp_path) == 0
    assert any(
        ("src/base_debt.py" in item for item in _cached_git_base_rule_ids(tmp_path))
    )
    cache_file = _single_git_base_cache_file(tmp_path)
    before_payload = cache_file.read_text(encoding="utf-8")
    assert lint_check(tmp_path) == 0
    assert cache_file.read_text(encoding="utf-8") == before_payload
