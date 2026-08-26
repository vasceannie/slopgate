"""Focused fixtures for repair CLI tests."""

from __future__ import annotations

import argparse
import json
from collections.abc import Generator
from pathlib import Path

import pytest
from slopgate._types import string_value
from slopgate.cli import repair
from slopgate.config import load_config
from slopgate.lint._config import reset_config
from slopgate.state import HookStateStore, RepairRequiredPayload
from tests.repair_cli.constants import (
    CLEAN_SOURCE,
    COMPLEXITY_RULE,
    DECOY_PATH,
    GENERATION_ONE,
    OVERSIZED_SOURCE,
    REPAIR_PATH,
    SLOPGATE_TOML,
)
from tests.repair_cli.support import ScopedLintCapture


@pytest.fixture
def repair_store(tmp_path: Path) -> HookStateStore:
    root = tmp_path.resolve()
    config = load_config(repo_root=root)
    return HookStateStore(config.trace_dir, scope=str(root))


@pytest.fixture
def repair_payload() -> RepairRequiredPayload:
    return RepairRequiredPayload(
        session_id="session-one",
        call_id="call-one",
        rule_ids=["QUALITY-LINT-001"],
        paths=[REPAIR_PATH],
    )


@pytest.fixture
def marked_repair_store(
    repair_store: HookStateStore, repair_payload: RepairRequiredPayload
) -> HookStateStore:
    repair_store.mark_repair_required(GENERATION_ONE, repair_payload)
    return repair_store


@pytest.fixture
def recorded_lint_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    repair_store: HookStateStore,
) -> tuple[
    ScopedLintCapture,
    list[tuple[Path, tuple[str, ...], tuple[str, ...]]],
]:
    payload = RepairRequiredPayload(
        session_id="session-one",
        call_id="call-one",
        rule_ids=[COMPLEXITY_RULE],
        paths=[REPAIR_PATH],
    )
    monkeypatch.chdir(tmp_path)
    repair_store.mark_repair_required(GENERATION_ONE, payload)
    capture = ScopedLintCapture()
    monkeypatch.setattr(repair, "_run_scoped_lint", capture)
    expected: list[tuple[Path, tuple[str, ...], tuple[str, ...]]] = [
        (
            tmp_path.resolve(),
            (str((tmp_path / REPAIR_PATH).resolve()),),
            (COMPLEXITY_RULE,),
        )
    ]
    return capture, expected


@pytest.fixture
def repair_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Generator[Path, None, None]:
    (tmp_path / "slopgate.toml").write_text(SLOPGATE_TOML, encoding="utf-8")
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text(CLEAN_SOURCE, encoding="utf-8")
    (src / "huge.py").write_text(OVERSIZED_SOURCE, encoding="utf-8")
    (tmp_path / "tests").mkdir()
    monkeypatch.chdir(tmp_path)
    reset_config()
    yield tmp_path
    reset_config()


@pytest.fixture
def known_debt_project(repair_project: Path) -> Path:
    (repair_project / "baselines.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "fixed-for-test",
                "rules": {
                    "oversized-module-soft": [
                        "oversized-module-soft|src/huge.py|huge.py|lines=371 (soft limit=350)"
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    return repair_project


@pytest.fixture
def preserved_baseline(repair_project: Path) -> tuple[Path, bytes]:
    baseline = repair_project / "baselines.json"
    baseline.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "generated_at": "fixed-for-test",
                "rules": {"unrelated-rule": ["unrelated-id"]},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return baseline, baseline.read_bytes()


@pytest.fixture
def targeted_debt_payload() -> RepairRequiredPayload:
    return RepairRequiredPayload(
        session_id="session-one",
        call_id="call-one",
        rule_ids=["PY-CODE-018"],
        paths=[DECOY_PATH],
    )


@pytest.fixture
def clean_path_payload() -> RepairRequiredPayload:
    return RepairRequiredPayload(
        session_id="session-one",
        call_id="call-one",
        rule_ids=[COMPLEXITY_RULE],
        paths=[REPAIR_PATH],
    )


@pytest.fixture(
    params=[
        pytest.param("absolute", id="absolute-project-escape"),
        pytest.param("../outside.py", id="relative-project-escape"),
    ]
)
def rejected_escape_verification(
    request: pytest.FixtureRequest,
    repair_project: Path,
    repair_store: HookStateStore,
) -> tuple[int, str | None]:
    case = request.param
    assert isinstance(case, str), "escape fixture cases must be path strings"
    outside = repair_project.parent / "outside.py"
    outside.write_text("value = 1\n", encoding="utf-8")
    path = {"absolute": str(outside), "../outside.py": "../outside.py"}[case]
    payload = RepairRequiredPayload(
        session_id="session-one",
        call_id="call-one",
        rule_ids=[COMPLEXITY_RULE],
        paths=[path],
    )
    repair_store.mark_repair_required(GENERATION_ONE, payload)
    result = repair.cmd_repair_verify(
        argparse.Namespace(cwd=str(repair_project), generation=GENERATION_ONE)
    )
    remaining = repair_store.get_repair_required()
    generation = None if remaining is None else string_value(remaining.get("generation"))
    return result, generation
