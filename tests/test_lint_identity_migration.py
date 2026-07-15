from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import slopgate.lint._baseline
from slopgate.cli.lint import lint_check
from slopgate.lint._config import load_config


LEGACY_ID = (
    "untested-production-code|src/pkg/module.py|coverage-000|"
    "static_test_reference_coverage=0%"
)
CANONICAL_ID = (
    "untested-public-api|src/pkg/module.py|public-api|"
    "public API lacks coverage evidence"
)


def _write_public_api_debt_repo(root: Path) -> None:
    package = root / "src" / "pkg"
    package.mkdir(parents=True)
    (package / "module.py").write_text(
        "def public_entrypoint() -> str:\n    return 'ok'\n",
        encoding="utf-8",
    )
    (root / "tests").mkdir()
    (root / "slopgate.toml").write_text(
        '[paths]\nsrc = "src"\ntests = "tests"\n',
        encoding="utf-8",
    )


def _initialize_feature_branch(root: Path) -> None:
    git = [
        "git",
        "-C",
        str(root),
        "-c",
        "user.name=Slopgate Tests",
        "-c",
        "user.email=slopgate-tests@example.invalid",
    ]
    subprocess.run([*git, "init", "-b", "main"], check=True, capture_output=True)
    subprocess.run([*git, "add", "."], check=True, capture_output=True)
    subprocess.run(
        [*git, "commit", "-m", "seed public API debt"],
        check=True,
        capture_output=True,
    )
    subprocess.run([*git, "checkout", "-b", "feature"], check=True, capture_output=True)


def _replace_git_base_cache_with_legacy_id(root: Path) -> None:
    cache_files = list((root / ".slopgate/cache/git-base-debt").glob("*.json"))
    assert len(cache_files) == 1, "the initial lint check should create one debt cache"
    cache_path = cache_files[0]
    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    payload["rules"] = {"untested-production-code": [LEGACY_ID]}
    cache_path.write_text(json.dumps(payload), encoding="utf-8")


def test_legacy_baseline_ids_normalize_to_canonical_module_identity(
    tmp_path: Path,
) -> None:
    load_config(tmp_path)
    (tmp_path / "baselines.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "rules": {"untested-production-code": [LEGACY_ID]},
            }
        ),
        encoding="utf-8",
    )

    loaded = slopgate.lint._baseline.load_baseline()

    assert loaded == {"untested-public-api": {CANONICAL_ID}}, (
        "legacy debt should compare as canonical public API debt"
    )


def test_rule_identity_normalization_is_idempotent_and_preserves_unrelated_ids() -> (
    None
):
    rules = {
        "untested-production-code": {LEGACY_ID},
        "other-rule": {"other-rule|src/x.py|x|mutable detail"},
    }

    normalized = slopgate.lint._baseline.normalize_lint_rule_ids(rules)

    assert slopgate.lint._baseline.normalize_lint_rule_ids(normalized) == normalized, (
        "identity migration should be idempotent"
    )
    assert normalized["other-rule"] == {"other-rule|src/x.py|x|mutable detail"}, (
        "unrelated stable IDs must remain byte-for-byte unchanged"
    )


def test_legacy_identity_changes_when_module_path_changes() -> None:
    moved = LEGACY_ID.replace("src/pkg/module.py", "src/pkg/moved.py")

    normalized = slopgate.lint._baseline.normalize_lint_rule_ids(
        {"untested-production-code": {LEGACY_ID, moved}}
    )

    assert len(normalized["untested-public-api"]) == 2, (
        "module path changes should produce distinct canonical identities"
    )


def test_baseline_save_rewrites_legacy_ids_canonically(tmp_path: Path) -> None:
    load_config(tmp_path)

    slopgate.lint._baseline.save_baseline_ids({"untested-production-code": {LEGACY_ID}})

    payload = json.loads((tmp_path / "baselines.json").read_text(encoding="utf-8"))
    assert payload["rules"] == {"untested-public-api": [CANONICAL_ID]}, (
        "the next successful baseline sync should persist only canonical IDs"
    )


def test_successful_lint_check_rewrites_legacy_debt_without_reporting_new(
    tmp_path: Path,
) -> None:
    _write_public_api_debt_repo(tmp_path)
    (tmp_path / "baselines.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "rules": {"untested-production-code": [LEGACY_ID]},
            }
        ),
        encoding="utf-8",
    )

    result = lint_check(tmp_path)

    payload = json.loads((tmp_path / "baselines.json").read_text(encoding="utf-8"))
    assert result == 0, "legacy public API debt should remain known during migration"
    assert payload["rules"] == {"untested-public-api": [CANONICAL_ID]}, (
        "a successful lint sync should rewrite legacy IDs canonically"
    )


def test_git_base_cache_uses_baseline_identity_normalization(tmp_path: Path) -> None:
    _write_public_api_debt_repo(tmp_path)
    _initialize_feature_branch(tmp_path)
    assert lint_check(tmp_path) == 0, (
        "git-base debt should be inherited on feature branches"
    )
    _replace_git_base_cache_with_legacy_id(tmp_path)

    result = lint_check(tmp_path)

    assert result == 0, (
        "legacy git-base debt should compare as canonical inherited debt"
    )


def test_legacy_cli_enablement_alias_only_targets_public_api(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"enabled_cli_rules": {"untested-production-code": False}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("SLOPGATE_CONFIG", str(config_path))

    config = load_config(tmp_path)

    assert config.enabled_cli_rules == {"untested-public-api": False}, (
        "legacy enablement must not toggle artifact or dead-internal collectors"
    )
