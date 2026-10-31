"""Gold fixtures mined from L1 PreToolUse cases and verified on the current engine."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from pytest import MonkeyPatch

from slopgate._types import object_dict
from slopgate.engine import evaluate_payload
from tests.test_engine import (
    keep_default_config,
    write_config_from_defaults,
    write_slopgate,
)

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "fixtures"
MIN_GOLD_TOTAL = 10
MIN_DISTINCT_RULES = 5
REQUIRED_PLATFORMS = ("claude", "opencode")
MAX_FILE_CHARS = 4000


def _gold_files() -> list[Path]:
    files = sorted(FIXTURES.glob("gold_*.json"))
    for child in sorted(FIXTURES.iterdir()):
        if child.is_dir():
            files.extend(sorted(child.glob("gold_*.json")))
    return files


def _gold_meta(path: Path) -> tuple[str, str, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    meta = payload.get("_gold") or {}
    platform = str(meta.get("platform") or (
        "opencode" if path.parent.name == "opencode" else "claude"
    ))
    kind = str(meta.get("label_kind") or "positive")
    rules = meta.get("current_rule_ids") or []
    primary = "_CLEAN" if kind == "true_negative" or not rules else str(rules[0])
    return platform, primary, kind


def _safe_relpath(path: str) -> str | None:
    text = path.replace("\\", "/").lstrip("/")
    if not text or ".." in Path(text).parts:
        return None
    if text.startswith("$"):
        text = text.split("/", 1)[-1] if "/" in text else ""
    return text or None


def _files_from_payload(payload: dict) -> list[dict[str, str]]:
    listed = payload.get("files")
    if isinstance(listed, list) and listed:
        return [item for item in listed if isinstance(item, dict)]
    tool_input = payload.get("tool_input") or {}
    path = tool_input.get("file_path") or tool_input.get("filePath") or tool_input.get("path")
    content = tool_input.get("content")
    if not path or not isinstance(content, str) or not content:
        return []
    rel = _safe_relpath(str(path))
    if not rel:
        return []
    overflow = len(content) - MAX_FILE_CHARS
    text = content if overflow <= 0 else f"{content[:MAX_FILE_CHARS]}...[truncated {overflow} chars]"
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return [{"path": rel, "sha256": digest, "text": text}]


def _materialize_workspace(repo: Path, payload: dict) -> None:
    for item in _files_from_payload(payload):
        path = item.get("path")
        rel = _safe_relpath(path) if isinstance(path, str) else None
        text = item.get("text")
        if not rel or not isinstance(text, str):
            continue
        dest = repo / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")


GOLD_CASES = tuple(
    (path, *_gold_meta(path))
    for path in _gold_files()
)
GOLD_POS = tuple(case for case in GOLD_CASES if case[3] != "true_negative")
GOLD_TN = tuple(case for case in GOLD_CASES if case[3] == "true_negative")


def test_gold_fixtures_exist() -> None:
    assert len(_gold_files()) >= MIN_GOLD_TOTAL, "expected at least 10 hand-verified gold fixtures"


def test_gold_coverage_meets_ci_minima() -> None:
    platforms = {platform for _path, platform, _rule, _kind in GOLD_CASES}
    rules = {rule for _path, _platform, rule, _kind in GOLD_CASES}
    missing = [name for name in REQUIRED_PLATFORMS if name not in platforms]
    assert not missing, f"gold missing required platforms: {missing}"
    assert len(GOLD_CASES) >= MIN_GOLD_TOTAL
    assert len(rules) >= MIN_DISTINCT_RULES, f"only {len(rules)} distinct gold rules"


def _replay_gold(
    gold_path: Path,
    platform: str,
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> list[str]:
    repo = write_slopgate(tmp_path / "gold_repo")
    write_config_from_defaults(tmp_path, monkeypatch, keep_default_config)
    monkeypatch.setenv("SLOPGATE_ROOT", str(tmp_path / "vf-root"))
    payload = object_dict(json.loads(gold_path.read_text(encoding="utf-8")))
    payload.pop("_gold", None)
    _materialize_workspace(repo, payload)
    payload.pop("files", None)
    payload["cwd"] = str(repo)
    result = evaluate_payload(payload, platform=platform)
    assert result.errors == [], f"{gold_path.name} errors={result.errors}"
    return [finding.rule_id for finding in result.findings]


@pytest.mark.parametrize(
    ("gold_path", "platform", "primary_rule"),
    [
        pytest.param(path, platform, primary, id=f"{platform}-{primary}-{path.name}")
        for path, platform, primary, _kind in GOLD_POS
    ],
)
def test_gold_positive_primary_still_fires(
    gold_path: Path,
    platform: str,
    primary_rule: str,
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    got = _replay_gold(gold_path, platform, tmp_path, monkeypatch)
    assert primary_rule in got, f"{gold_path.name} missing primary {primary_rule} in {got}"


@pytest.mark.parametrize(
    ("gold_path", "platform"),
    [
        pytest.param(path, platform, id=f"{platform}-tn-{path.name}")
        for path, platform, _primary, _kind in GOLD_TN
    ],
)
def test_gold_true_negative_stays_clean(
    gold_path: Path,
    platform: str,
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    got = _replay_gold(gold_path, platform, tmp_path, monkeypatch)
    assert got == [], f"{gold_path.name} expected clean, got {got}"
