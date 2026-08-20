"""Result trace provenance: paths, languages, version, and fingerprints."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from slopgate import __version__
from slopgate._types import ObjectDict, is_object_dict
from slopgate.engine._fingerprints import (
    effective_policy_fingerprint,
    guidance_fingerprint,
)
from tests.test_engine import (
    MonkeyPatch,
    keep_default_config,
    pretool_bash_payload,
    write_config_from_defaults,
    write_slopgate,
    evaluate_payload,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from slopgate.models import RuntimeConfig

FINGERPRINT_FIELDS = frozenset(
    {
        "candidate_paths",
        "languages",
        "slopgate_version",
        "effective_policy_fingerprint",
        "guidance_fingerprint",
    }
)


def _latest_result_row(tmp_path: Path) -> dict[str, object]:
    results_path = tmp_path / "vf-root" / "logs" / "results.jsonl"
    lines = results_path.read_text(encoding="utf-8").strip().splitlines()
    assert lines
    return json.loads(lines[-1])


def _evaluate_repo_write(
    tmp_path: Path, monkeypatch: MonkeyPatch, repo_name: str
) -> dict[str, object]:
    repo = write_slopgate(tmp_path / repo_name)
    write_config_from_defaults(tmp_path, monkeypatch, keep_default_config)
    monkeypatch.setenv("SLOPGATE_ROOT", str(tmp_path / "vf-root"))
    _ = evaluate_payload(pretool_bash_payload(repo, "git status"))
    return _latest_result_row(tmp_path)


def _load_runtime_config(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    mutate: Callable[[ObjectDict], None],
) -> RuntimeConfig:
    from slopgate.config import load_config

    write_config_from_defaults(tmp_path, monkeypatch, mutate)
    return load_config()


def test_result_row_records_provenance_fields(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    row = _evaluate_repo_write(tmp_path, monkeypatch, "repo_provenance")

    assert FINGERPRINT_FIELDS <= row.keys(), (
        "result rows must carry path, language, version, and fingerprint provenance"
    )
    assert row["slopgate_version"] == __version__
    assert isinstance(row["candidate_paths"], list)
    assert isinstance(row["languages"], list)


@pytest.mark.parametrize(
    "field", ["effective_policy_fingerprint", "guidance_fingerprint"]
)
def test_result_row_fingerprints_are_sha256_hex(
    tmp_path: Path, monkeypatch: MonkeyPatch, field: str
) -> None:
    row = _evaluate_repo_write(tmp_path, monkeypatch, f"repo_{field}")

    value = str(row[field])
    assert len(value) == 64, f"{field} must be a sha256 hex digest"
    int(value, 16)


def test_fingerprints_are_deterministic_for_same_config(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    first = _evaluate_repo_write(tmp_path, monkeypatch, "repo_fp_a")
    second = _evaluate_repo_write(tmp_path, monkeypatch, "repo_fp_b")

    assert first["effective_policy_fingerprint"] == second[
        "effective_policy_fingerprint"
    ], "same config and rule sources must yield identical policy fingerprints"
    assert first["guidance_fingerprint"] == second["guidance_fingerprint"], (
        "same config and guidance sources must yield identical guidance fingerprints"
    )


def test_policy_fingerprint_tracks_rule_enablement(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    def disable_rule(defaults: dict[str, object]) -> None:
        enabled: dict[str, object] = {}
        raw_enabled = defaults.get("enabled_rules")
        if is_object_dict(raw_enabled):
            enabled.update(raw_enabled)
        enabled["PY-CODE-013"] = False
        defaults["enabled_rules"] = enabled

    baseline = _load_runtime_config(tmp_path, monkeypatch, keep_default_config)
    mutated = _load_runtime_config(tmp_path, monkeypatch, disable_rule)

    assert effective_policy_fingerprint(baseline) != effective_policy_fingerprint(
        mutated
    ), "disabling a rule must change effective policy identity"


def test_guidance_change_leaves_policy_fingerprint_stable(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    def retune_reminder(defaults: dict[str, object]) -> None:
        defaults["search_reminder_message"] = "search first, then write v2"

    baseline = _load_runtime_config(tmp_path, monkeypatch, keep_default_config)
    mutated = _load_runtime_config(tmp_path, monkeypatch, retune_reminder)

    assert effective_policy_fingerprint(baseline) == effective_policy_fingerprint(
        mutated
    ), "guidance-only config must not change policy identity"
    assert guidance_fingerprint(baseline) != guidance_fingerprint(mutated), (
        "guidance config changes must change guidance identity"
    )


def test_regex_rule_message_changes_guidance_fingerprint(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    baseline = _load_runtime_config(tmp_path, monkeypatch, keep_default_config)
    mutated = _load_runtime_config(tmp_path, monkeypatch, keep_default_config)
    mutated.regex_rules[0].message = "rule guidance v2"

    assert guidance_fingerprint(baseline) != guidance_fingerprint(mutated), (
        "regex rule messages must change guidance identity"
    )


def test_rule_source_change_alters_policy_fingerprint_without_version_bump(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    config = _load_runtime_config(tmp_path, monkeypatch, keep_default_config)
    rules_root = tmp_path / "rules_src"
    rules_root.mkdir()
    source = rules_root / "sample_rule.py"
    source.write_text("RULE_BODY_V1 = 1\n", encoding="utf-8")

    before = effective_policy_fingerprint(config, rules_root=rules_root)
    source.write_text("RULE_BODY_V2_WITH_MORE_CONTENT = 2\n", encoding="utf-8")
    after = effective_policy_fingerprint(config, rules_root=rules_root)

    assert before != after, (
        "enforcement source changes must alter policy identity even when the"
        " package version is unchanged"
    )


def test_staging_source_change_does_not_alter_policy_fingerprint(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    config = _load_runtime_config(tmp_path, monkeypatch, keep_default_config)
    rules_root = tmp_path / "rules_src"
    staging_root = rules_root / "python_ast" / "_staging"
    staging_root.mkdir(parents=True)
    (rules_root / "active_rule.py").write_text("ACTIVE_RULE = 1\n", encoding="utf-8")
    staging_source = staging_root / "draft_rule.py"
    staging_source.write_text("DRAFT_RULE = 1\n", encoding="utf-8")

    before = effective_policy_fingerprint(config, rules_root=rules_root)
    staging_source.write_text("DRAFT_RULE = 2\n", encoding="utf-8")
    after = effective_policy_fingerprint(config, rules_root=rules_root)

    assert before == after, (
        "non-enforcing staging sources must not change effective policy identity"
    )
