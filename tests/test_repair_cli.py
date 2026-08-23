from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import pytest
from hypothesis import given, strategies
from slopgate._types import ObjectDict
from slopgate.cli import repair as repair_mod
from slopgate.cli.lint import cmd_lint
from slopgate.cli.repair import add_repair_parsers, cmd_repair_status, cmd_repair_verify
from slopgate.lint._config import reset_config
from slopgate.state import RepairRequiredPayload

_GENERATION_ONE = "generation-one"
_GENERATION_TWO = "generation-two"
_REPAIR_PATH = "src/app.py"
_DECOY_PATH = "src/huge.py"
_COMPLEXITY_RULE = "PY-CODE-015"
_CLEAN_SOURCE = (
    "from __future__ import annotations\n\n\ndef answer() -> int:\n    return 1\n"
)
_OVERSIZED_SOURCE = "from __future__ import annotations\n" + "# filler\n" * 370
_SLOPGATE_TOML = "[slopgate]\nenabled = true\n"


def _mark_repair(
    tmp_path: Path,
    generation: str,
    *,
    rule_ids: list[str] | None = None,
    paths: list[str] | None = None,
) -> None:
    repair_mod._store(str(tmp_path)).mark_repair_required(
        generation,
        RepairRequiredPayload(
            session_id="session-one",
            call_id="call-one",
            rule_ids=rule_ids or ["QUALITY-LINT-001"],
            paths=paths or [_REPAIR_PATH],
        ),
    )


def _write_repair_project(root: Path) -> None:
    (root / "slopgate.toml").write_text(_SLOPGATE_TOML, encoding="utf-8")
    src = root / "src"
    src.mkdir()
    (src / "app.py").write_text(_CLEAN_SOURCE, encoding="utf-8")
    (src / "huge.py").write_text(_OVERSIZED_SOURCE, encoding="utf-8")
    (root / "tests").mkdir()


def _verify(tmp_path: Path, generation: str) -> int:
    return cmd_repair_verify(
        argparse.Namespace(cwd=str(tmp_path), generation=generation)
    )


def _required(tmp_path: Path) -> ObjectDict | None:
    return repair_mod._store(str(tmp_path)).get_repair_required()


def _expected_path_capture(
    tmp_path: Path,
) -> list[tuple[Path, tuple[str, ...], tuple[str, ...]]]:
    return [
        (
            tmp_path.resolve(),
            (str((tmp_path / _REPAIR_PATH).resolve()),),
            (_COMPLEXITY_RULE,),
        )
    ]


def _verify_project(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    generation: str,
    rule_ids: list[str],
    paths: list[str],
) -> int:
    _write_repair_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    _mark_repair(tmp_path, generation, rule_ids=rule_ids, paths=paths)
    reset_config()
    try:
        return _verify(tmp_path, generation)
    finally:
        reset_config()


def test_repair_status_command_reports_clean_state(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    result = cmd_repair_status(argparse.Namespace(cwd=str(tmp_path)))

    assert result == 0, "Repair status should succeed for an isolated worktree"
    assert json.loads(capsys.readouterr().out) == {"status": "clean"}, (
        "An unmarked worktree should report clean state"
    )


def test_repair_verify_command_is_idempotent_when_clean(tmp_path: Path) -> None:
    result = cmd_repair_verify(
        argparse.Namespace(cwd=str(tmp_path), generation="missing")
    )

    assert result == 0, "Verification should be a no-op when no repair is pending"


@given(generation=strategies.text(min_size=1, max_size=32))
def test_repair_verify_accepts_arbitrary_generation_tokens(
    generation: str,
) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        result = cmd_repair_verify(
            argparse.Namespace(cwd=tmp_dir, generation=generation)
        )

    assert result == 0, "Clean verification should not depend on generation syntax"


def _capture_scoped_lint(
    monkeypatch: pytest.MonkeyPatch, returncode: int = 0
) -> list[tuple[Path, tuple[str, ...], tuple[str, ...]]]:
    captured: list[tuple[Path, tuple[str, ...], tuple[str, ...]]] = []

    def _run(
        cwd: Path, paths: list[str], rule_ids: list[str]
    ) -> int:
        captured.append((cwd, tuple(paths), tuple(rule_ids)))
        return returncode

    monkeypatch.setattr(repair_mod, "_run_scoped_lint", _run)
    return captured


def test_repair_verify_lints_recorded_paths_and_rule_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _mark_repair(
        tmp_path,
        _GENERATION_ONE,
        rule_ids=[_COMPLEXITY_RULE],
        paths=[_REPAIR_PATH],
    )
    captured = _capture_scoped_lint(monkeypatch)
    result = _verify(tmp_path, _GENERATION_ONE)
    remaining = _required(tmp_path)

    assert result == 0, "matching generation should verify and clear"
    assert captured == _expected_path_capture(tmp_path), (
        "verification must lint the generation paths and rule IDs, not lint check"
    )
    assert remaining is None, "successful verification should clear the matching generation"


def test_repair_verify_generation_mismatch_skips_lint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _mark_repair(tmp_path, _GENERATION_ONE)
    captured = _capture_scoped_lint(monkeypatch)
    result = _verify(tmp_path, _GENERATION_TWO)
    remaining = _required(tmp_path)

    assert result == 1, "generation mismatch must fail closed"
    assert captured == [], "generation mismatch must not start a scoped lint"
    assert json.loads(capsys.readouterr().out) == {"status": "generation_mismatch"}, (
        "generation mismatch must report status without clearing"
    )
    assert remaining is not None, "generation mismatch must retain REPAIR_REQUIRED"
    assert remaining["generation"] == _GENERATION_ONE, (
        "generation mismatch must keep the armed generation"
    )


def test_repair_verify_dirty_scoped_lint_retains_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mark_repair(tmp_path, _GENERATION_ONE)
    _ = _capture_scoped_lint(monkeypatch, returncode=1)
    result = cmd_repair_verify(
        argparse.Namespace(cwd=str(tmp_path), generation=_GENERATION_ONE)
    )
    remaining = repair_mod._store(str(tmp_path)).get_repair_required()

    assert result == 1, "dirty scoped lint must fail closed"
    assert remaining is not None, "dirty scoped lint must retain REPAIR_REQUIRED"
    assert remaining["generation"] == _GENERATION_ONE, (
        "dirty scoped lint must keep the armed generation"
    )


def test_repair_verify_does_not_clear_replaced_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _mark_repair(tmp_path, _GENERATION_ONE)
    store = repair_mod._store(str(tmp_path))

    def _run(_cwd: Path, _paths: list[str], _rule_ids: list[str]) -> int:
        _mark_repair(tmp_path, _GENERATION_TWO)
        return 0

    monkeypatch.setattr(repair_mod, "_run_scoped_lint", _run)

    result = cmd_repair_verify(
        argparse.Namespace(cwd=str(tmp_path), generation=_GENERATION_ONE)
    )
    required = store.get_repair_required()

    assert result == 1, "a replaced generation must fail closed"
    assert required is not None, "newer repair state must survive the stale verify"
    assert required["generation"] == _GENERATION_TWO, (
        "verification must not clear a newer repair generation"
    )


def test_repair_verify_clears_when_only_recorded_paths_are_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _verify_project(
        tmp_path,
        monkeypatch,
        _GENERATION_ONE,
        [_COMPLEXITY_RULE],
        [_REPAIR_PATH],
    )
    remaining = _required(tmp_path)

    assert result == 0, "path-scoped verify should ignore unrelated full-repo debt"
    assert remaining is None, "clean recorded paths should clear the matching generation"


def test_repair_verify_retains_when_recorded_path_is_dirty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result = _verify_project(
        tmp_path,
        monkeypatch,
        _GENERATION_ONE,
        ["PY-CODE-018"],
        [_DECOY_PATH],
    )
    remaining = _required(tmp_path)

    assert result != 0, "dirty recorded paths must not unlock the generation"
    assert remaining is not None, "dirty recorded paths must retain REPAIR_REQUIRED"
    assert remaining["generation"] == _GENERATION_ONE, (
        "dirty recorded paths must keep the armed generation"
    )


def test_repair_verify_fails_on_known_targeted_debt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_repair_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "baselines.json").write_text(
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
    _mark_repair(
        tmp_path,
        _GENERATION_ONE,
        rule_ids=["PY-CODE-018"],
        paths=[_DECOY_PATH],
    )
    reset_config()

    try:
        result = _verify(tmp_path, _GENERATION_ONE)
    finally:
        reset_config()

    assert result == 1, "known targeted debt must fail all-violation verification"
    remaining = _required(tmp_path)
    assert remaining is not None
    assert remaining["generation"] == _GENERATION_ONE


def test_repair_verify_does_not_sync_baseline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_repair_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    baseline = tmp_path / "baselines.json"
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
    before = baseline.read_bytes()
    _mark_repair(
        tmp_path,
        _GENERATION_ONE,
        rule_ids=[_COMPLEXITY_RULE],
        paths=[_REPAIR_PATH],
    )
    reset_config()

    try:
        result = _verify(tmp_path, _GENERATION_ONE)
    finally:
        reset_config()

    assert result == 0, "clean verification should clear the repair generation"
    assert baseline.read_bytes() == before, (
        "repair verification must not prune or rewrite the repository baseline"
    )


def test_repair_verify_retains_generation_when_recorded_path_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_repair_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    _mark_repair(
        tmp_path,
        _GENERATION_ONE,
        rule_ids=[_COMPLEXITY_RULE],
        paths=["src/does-not-exist.py"],
    )
    reset_config()

    try:
        result = _verify(tmp_path, _GENERATION_ONE)
    finally:
        reset_config()

    assert result == 1, "unresolvable recorded paths must fail closed"
    assert "do not resolve to files" in capsys.readouterr().out
    remaining = _required(tmp_path)
    assert remaining is not None, "missing paths must retain REPAIR_REQUIRED"
    assert remaining["generation"] == _GENERATION_ONE


def test_locate_repair_path_rejects_project_escapes(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("value = 1\n", encoding="utf-8")

    assert repair_mod._locate_repair_path(project, str(outside)) is None
    assert repair_mod._locate_repair_path(project, "../outside.py") is None


def test_full_repo_lint_check_still_scans_unrelated_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_repair_project(tmp_path)
    monkeypatch.chdir(tmp_path)
    reset_config()
    try:
        result = cmd_lint(argparse.Namespace(lint_command="check", details=False))
    finally:
        reset_config()
    output = capsys.readouterr().out

    assert result == 1, "full-repo lint check must still fail on repo-wide violations"
    assert "oversized-module" in output, (
        "lint check must keep LINT_SCOPE_ALL and report the decoy file"
    )


def test_repair_parser_registers_status_and_verify() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")
    add_repair_parsers(sub)

    status = parser.parse_args(["repair", "status"])
    verify = parser.parse_args(["repair", "verify", "--generation", "gen-1"])

    assert callable(status.func), "Repair status should register a CLI handler"
    assert callable(verify.func), "Repair verify should register a CLI handler"
