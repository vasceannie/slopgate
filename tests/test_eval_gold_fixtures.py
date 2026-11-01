"""Gold fixtures mined from L1 PreToolUse cases and verified on the current engine."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from pytest import MonkeyPatch

from slopgate._types import ObjectDict, object_dict, object_list
from slopgate.engine import evaluate_payload
from tests.adapters.test_opencode_projection.support import (
    raw_payload,
)
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
V2_SAFE_WRITE_CONTENT = "VALUE = 1\n"
V2_UNSAFE_WRITE_CONTENT = "def broken(:\n"


def _gold_files() -> list[Path]:
    files = sorted(FIXTURES.glob("gold_*.json"))
    for child in sorted(FIXTURES.iterdir()):
        if child.is_dir():
            files.extend(sorted(child.glob("gold_*.json")))
    return files


@dataclass(frozen=True, slots=True)
class GoldCase:
    path: Path
    platform: str
    primary_rule: str
    label_kind: str


def _gold_case(path: Path) -> GoldCase:
    payload = json.loads(path.read_text(encoding="utf-8"))
    meta = payload.get("_gold") or {}
    platform = str(
        meta.get("platform")
        or ("opencode" if path.parent.name == "opencode" else "claude")
    )
    kind = str(meta.get("label_kind") or "positive")
    rules = meta.get("current_rule_ids") or []
    primary = "_CLEAN" if kind == "true_negative" or not rules else str(rules[0])
    return GoldCase(path, platform, primary, kind)


def _payload_for_case(case: GoldCase) -> ObjectDict:
    return object_dict(json.loads(case.path.read_text(encoding="utf-8")))


def _is_legacy_opencode_mutation(case: GoldCase) -> bool:
    """Identify archived v1 mutations that are not valid V2 inputs.

    These mined OpenCode payloads predate the top-level V2 contract and carry
    hashline ``edits`` plus ``filePath``/``file_path`` (or an embedded V1
    projection).  They must remain replayed as fail-closed mutations rather
    than being treated as current V2 true negatives.
    """
    if case.platform != "opencode":
        return False
    payload = _payload_for_case(case)
    if "opencode_tool_contract_version" in payload:
        return False
    tool_input = object_dict(payload.get("tool_input"))
    projection = object_dict(tool_input.get("_slopgate_projection"))
    if projection.get("contract_version") == "slopgate-opencode-projection-v1":
        return True
    return "edits" in tool_input and any(
        key in tool_input for key in ("filePath", "file_path")
    )


def _replay_current_v2_write(
    content: str,
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> list[str]:
    repo = write_slopgate(tmp_path / "v2_repo")
    write_config_from_defaults(tmp_path, monkeypatch, keep_default_config)
    monkeypatch.setenv("SLOPGATE_ROOT", str(tmp_path / "v2-root"))
    payload = raw_payload(repo, "write", {"path": "src/app.py", "content": content})
    result = evaluate_payload(payload, platform="opencode")
    assert result.errors == [], f"V2 replay errors={result.errors}"
    return [finding.rule_id for finding in result.findings]


def test_current_v2_safe_write_replay_stays_clean(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    got = _replay_current_v2_write(V2_SAFE_WRITE_CONTENT, tmp_path, monkeypatch)
    assert got == [], f"complete safe V2 write expected clean, got {got}"


def test_current_v2_unsafe_write_replay_uses_native_rules(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    got = _replay_current_v2_write(V2_UNSAFE_WRITE_CONTENT, tmp_path, monkeypatch)
    assert "PY-AST-001" in got, f"native V2 write must catch unsafe content: {got}"
    assert "OC-PROJECTION-001" not in got, (
        f"valid V2 mutation must not be denied as an unresolved projection: {got}"
    )


def _safe_relpath(path: str) -> str | None:
    text = path.replace("\\", "/").lstrip("/")
    if not text or ".." in Path(text).parts:
        return None
    if text.startswith("$"):
        text = text.split("/", 1)[-1] if "/" in text else ""
    return text or None


def _files_from_payload(payload: ObjectDict) -> list[ObjectDict]:
    listed = object_list(payload.get("files"))
    if listed:
        return [object_dict(item) for item in listed if isinstance(item, dict)]
    tool_input = object_dict(payload.get("tool_input"))
    path = (
        tool_input.get("file_path")
        or tool_input.get("filePath")
        or tool_input.get("path")
    )
    content = tool_input.get("content")
    if not path or not isinstance(content, str) or not content:
        return []
    rel = _safe_relpath(str(path))
    if not rel:
        return []
    overflow = len(content) - MAX_FILE_CHARS
    text = (
        content
        if overflow <= 0
        else f"{content[:MAX_FILE_CHARS]}...[truncated {overflow} chars]"
    )
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return [{"path": rel, "sha256": digest, "text": text}]


def _materialize_workspace(repo: Path, payload: ObjectDict) -> None:
    for item in _files_from_payload(payload):
        path = item.get("path")
        rel = _safe_relpath(path) if isinstance(path, str) else None
        text = item.get("text")
        if not rel or not isinstance(text, str):
            continue
        dest = repo / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")


GOLD_CASES = tuple(_gold_case(path) for path in _gold_files())
GOLD_POS = tuple(case for case in GOLD_CASES if case.label_kind != "true_negative")
GOLD_TN = tuple(case for case in GOLD_CASES if case.label_kind == "true_negative")
GOLD_LEGACY_OPENCODE_TN = tuple(
    case for case in GOLD_TN if _is_legacy_opencode_mutation(case)
)
GOLD_CURRENT_TN = tuple(
    case for case in GOLD_TN if not _is_legacy_opencode_mutation(case)
)


def test_gold_fixtures_exist() -> None:
    assert len(_gold_files()) >= MIN_GOLD_TOTAL, (
        "expected at least 10 hand-verified gold fixtures"
    )


def test_gold_coverage_meets_ci_minima() -> None:
    platforms = {case.platform for case in GOLD_CASES}
    rules = {case.primary_rule for case in GOLD_CASES}
    missing = [name for name in REQUIRED_PLATFORMS if name not in platforms]
    assert not missing, f"gold missing required platforms: {missing}"
    assert len(GOLD_CASES) >= MIN_GOLD_TOTAL
    assert len(rules) >= MIN_DISTINCT_RULES, f"only {len(rules)} distinct gold rules"


def _replay_gold(
    case: GoldCase,
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> list[str]:
    repo = write_slopgate(tmp_path / "gold_repo")
    write_config_from_defaults(tmp_path, monkeypatch, keep_default_config)
    monkeypatch.setenv("SLOPGATE_ROOT", str(tmp_path / "vf-root"))
    payload = _payload_for_case(case)
    payload.pop("_gold", None)
    _materialize_workspace(repo, payload)
    payload.pop("files", None)
    payload["cwd"] = str(repo)
    result = evaluate_payload(payload, platform=case.platform)
    assert result.errors == [], f"{case.path.name} errors={result.errors}"
    return [finding.rule_id for finding in result.findings]


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(case, id=f"{case.platform}-{case.primary_rule}-{case.path.name}")
        for case in GOLD_POS
    ],
)
def test_gold_positive_primary_still_fires(
    case: GoldCase,
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    got = _replay_gold(case, tmp_path, monkeypatch)
    assert case.primary_rule in got, (
        f"{case.path.name} missing primary {case.primary_rule} in {got}"
    )


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(
            case,
            id=f"{case.platform}-legacy-tn-{case.path.name}",
        )
        for case in GOLD_LEGACY_OPENCODE_TN
    ],
)
def test_gold_legacy_opencode_mutation_is_fail_closed(
    case: GoldCase,
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    """Archived v1 hashline/filePath payloads are denied under the V2 contract."""
    got = _replay_gold(case, tmp_path, monkeypatch)
    assert "OC-PROJECTION-001" in got, (
        f"{case.path.name} legacy mutation must be denied by projection: {got}"
    )


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(case, id=f"{case.platform}-tn-{case.path.name}")
        for case in GOLD_CURRENT_TN
    ],
)
def test_gold_true_negative_stays_clean(
    case: GoldCase,
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
) -> None:
    got = _replay_gold(case, tmp_path, monkeypatch)
    assert got == [], f"{case.path.name} expected clean, got {got}"
