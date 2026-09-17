"""Gold fixtures mined from L1 PreToolUse cases and verified on the current engine."""

from __future__ import annotations

import json
from pathlib import Path

from slopgate._types import object_dict
from slopgate.engine import evaluate_payload
from tests.test_engine import (
    MonkeyPatch,
    keep_default_config,
    write_config_from_defaults,
    write_slopgate,
)

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "fixtures"


def _gold_files() -> list[Path]:
    files = sorted(FIXTURES.glob("gold_*.json"))
    files.extend(sorted((FIXTURES / "opencode").glob("gold_*.json")))
    return files


def test_gold_fixtures_exist() -> None:
    assert len(_gold_files()) >= 10, "expected at least 10 hand-verified gold fixtures"


def test_gold_fixtures_replay_without_errors(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    files = _gold_files()
    assert files, "no gold fixtures found"
    repo = write_slopgate(tmp_path / "gold_repo")
    write_config_from_defaults(tmp_path, monkeypatch, keep_default_config)
    monkeypatch.setenv("SLOPGATE_ROOT", str(tmp_path / "vf-root"))
    for path in files:
        payload = object_dict(json.loads(path.read_text(encoding="utf-8")))
        platform = "opencode" if path.parent.name == "opencode" else "claude"
        meta = payload.pop("_gold", None)
        if isinstance(meta, dict) and meta.get("platform"):
            platform = str(meta["platform"])
        payload["cwd"] = str(repo)
        result = evaluate_payload(payload, platform=platform)
        assert result.errors == [], f"{path.name} errors={result.errors}"
        got = [finding.rule_id for finding in result.findings]
        if isinstance(meta, dict) and meta.get("label_kind") == "true_negative":
            assert got == [], f"{path.name} expected clean, got {got}"
        elif isinstance(meta, dict) and meta.get("current_rule_ids"):
            expected = [str(item) for item in meta["current_rule_ids"]]
            assert expected[0] in got, (
                f"{path.name} missing primary {expected[0]} in {got}"
            )
