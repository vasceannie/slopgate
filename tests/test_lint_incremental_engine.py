"""Incremental lint engine contracts: parse-once, enablement, cache, profile."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import pytest

from slopgate.cli.cli import build_parser
from slopgate.cli.lint import cmd_lint
from slopgate.constants import (
    LINT_ENV_CLI,
    LINT_ENV_NO_INDEX,
    LINT_ENV_PROFILE,
    LINT_ENV_TRUE,
)
from slopgate.lint._baseline import Violation
from slopgate.lint._collectors import (
    CollectorRunOptions,
    run_all_collectors,
    run_touched_collectors,
)
from slopgate.lint._collector_groups.incremental import IncrementalContext, dirty_relatives
from slopgate.lint._config import load_config, reset_config, set_config
from slopgate.lint._detectors.line_length import detect_long_lines
from slopgate.lint._helpers import ParsedFile
from slopgate.lint._parse_errors import detect_python_parse_errors

GIT_TEST_USER_NAME = "Slopgate Tests"
GIT_TEST_USER_EMAIL = "slopgate-tests@example.invalid"
LONG_LINE = "value = " + " + ".join(["1"] * 80) + "\n"


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


def _write_enrolled_source(root: Path, relative: str, body: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _configure_root(root: Path) -> None:
    (root / "slopgate.toml").write_text(
        "[slopgate]\nenabled = true\n", encoding="utf-8"
    )
    set_config(load_config(root))


def _seed_committed_sources(root: Path, files: dict[str, str]) -> list[Path]:
    _configure_root(root)
    written = [_write_enrolled_source(root, relative, body) for relative, body in files.items()]
    _run_git(root, "init", "-b", "main")
    _run_git(root, "add", "slopgate.toml", *files)
    _run_git(root, "commit", "-m", "seed", test_identity=True)
    return written


def _seed_git_base_feature_repo(root: Path) -> None:
    (root / "slopgate.toml").write_text('[paths]\nsrc = "src"\n', encoding="utf-8")
    src = root / "src"
    src.mkdir()
    (src / "base_debt.py").write_text("x = 1\n" * 130, encoding="utf-8")
    _run_git(root, "init", "-b", "main")
    _run_git(root, "add", "slopgate.toml", "src/base_debt.py")
    _run_git(root, "commit", "-m", "seed base debt", test_identity=True)
    _run_git(root, "checkout", "-b", "feature")


def test_parse_errors_come_from_attempts_without_reparse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_root(tmp_path)
    broken = _write_enrolled_source(tmp_path, "src/pkg/broken.py", "def broken(:\n")
    calls: list[list[Path]] = []

    def tracked(paths: list[Path]) -> list[Violation]:
        calls.append(list(paths))
        raise AssertionError("python-parse-error should not re-parse")

    monkeypatch.setattr(
        "slopgate.lint._parse_errors.detect_python_parse_errors", tracked
    )
    results = dict(run_all_collectors([broken], []))
    reset_config()
    assert {
        "calls": calls,
        "identifier": results["python-parse-error"][0].identifier,
        "legacy_identifier": detect_python_parse_errors([broken])[0].identifier,
    } == {
        "calls": [],
        "identifier": "line-1",
        "legacy_identifier": "line-1",
    }


def test_disabled_opt_in_collector_is_not_invoked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_root(tmp_path)
    source = _write_enrolled_source(
        tmp_path, "src/pkg/app.py", "def answer() -> int:\n    return 1\n"
    )
    calls: list[int] = []

    def tracked(parsed: list[ParsedFile]) -> list[Violation]:
        calls.append(len(parsed))
        return []

    monkeypatch.setattr(
        "slopgate.lint._detectors.source_interop.detect_dead_code", tracked
    )
    dict(run_all_collectors([source], []))
    reset_config()
    assert calls == []


def test_touched_collectors_skip_constant_index_rebuild(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _configure_root(tmp_path)
    source = _write_enrolled_source(
        tmp_path, "src/pkg/app.py", "def answer() -> int:\n    return 1\n"
    )

    def fail_build(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("touched collectors should not rebuild constant index")

    monkeypatch.setattr(
        "slopgate.quality.constant_index.build_project_constant_index",
        fail_build,
    )
    names = {name for name, _violations in run_touched_collectors([source], [])}
    reset_config()
    assert "python-parse-error" in names


def _long_line_cache_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, object]:
    first, second = _seed_committed_sources(
        tmp_path, {"src/pkg/one.py": LONG_LINE, "src/pkg/two.py": LONG_LINE}
    )
    counts: list[int] = []

    def tracked(parsed: list[ParsedFile]) -> list[Violation]:
        counts.append(len(parsed))
        return detect_long_lines(parsed)

    monkeypatch.setattr(
        "slopgate.lint._detectors.line_length.detect_long_lines", tracked
    )
    options = CollectorRunOptions(persist_index=True, use_index=True)
    first_hits = dict(run_all_collectors([first, second], [], options))
    second_hits = dict(run_all_collectors([first, second], [], options))
    reset_config()
    return {
        "counts": counts,
        "first": len(first_hits["long-line"]),
        "second": len(second_hits["long-line"]),
    }


def test_file_local_collectors_use_cached_clean_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _long_line_cache_contract(tmp_path, monkeypatch) == {
        "counts": [2],
        "first": 2,
        "second": 2,
    }


def _profiled_git_base_outputs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> dict[str, object]:
    _seed_git_base_feature_repo(tmp_path)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(LINT_ENV_CLI, LINT_ENV_TRUE)
    monkeypatch.setenv(LINT_ENV_PROFILE, LINT_ENV_TRUE)
    reset_config()
    first = cmd_lint(argparse.Namespace(lint_command="check", details=False, profile=True))
    first_out = capsys.readouterr().out
    second = cmd_lint(
        argparse.Namespace(lint_command="check", details=False, profile=True)
    )
    second_out = capsys.readouterr().out
    reset_config()
    return {
        "first": first,
        "second": second,
        "miss": "git-base: MISS scan=" in first_out,
        "hit": "git-base: HIT sha=" in second_out,
        "profile": "profile:" in second_out,
    }


def test_profile_reports_git_base_hit_after_cache(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert _profiled_git_base_outputs(tmp_path, monkeypatch, capsys) == {
        "first": 0,
        "second": 0,
        "miss": True,
        "hit": True,
        "profile": True,
    }


def test_lint_check_scan_flags_parse() -> None:
    parsed = build_parser().parse_args(
        ["lint", "check", "--profile", "--full", "--no-index"]
    )
    assert (parsed.profile, parsed.full, parsed.no_index, parsed.lint_command) == (
        True,
        True,
        True,
        "check",
    )


def _committed_content_change_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, object]:
    first, second = _seed_committed_sources(
        tmp_path, {"src/pkg/one.py": LONG_LINE, "src/pkg/two.py": LONG_LINE}
    )
    options = CollectorRunOptions(persist_index=True, use_index=True)
    dict(run_all_collectors([first, second], [], options))
    first.write_text("def ok() -> int:\n    return 1\n", encoding="utf-8")
    _run_git(tmp_path, "add", "src/pkg/one.py")
    _run_git(tmp_path, "commit", "-m", "clean one", test_identity=True)
    counts: list[int] = []

    def tracked(parsed: list[ParsedFile]) -> list[Violation]:
        counts.append(len(parsed))
        return detect_long_lines(parsed)

    monkeypatch.setattr(
        "slopgate.lint._detectors.line_length.detect_long_lines", tracked
    )
    hits = dict(run_all_collectors([first, second], [], options))
    reset_config()
    return {"counts": counts, "hits": len(hits["long-line"])}


def test_file_local_cache_invalidates_after_clean_head_content_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _committed_content_change_contract(tmp_path, monkeypatch) == {
        "counts": [1],
        "hits": 1,
    }


def _warm_parse_skip_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, object]:
    from slopgate.lint._helpers.parsing import parse_file_attempt

    first, second = _seed_committed_sources(
        tmp_path, {"src/pkg/one.py": LONG_LINE, "src/pkg/two.py": LONG_LINE}
    )
    options = CollectorRunOptions(persist_index=True, use_index=True)
    dict(run_all_collectors([first, second], [], options))
    calls: list[str] = []

    def tracked(path: Path):
        calls.append(path.name)
        return parse_file_attempt(path)

    monkeypatch.setattr(
        "slopgate.lint._helpers.parsing.parse_file_attempt", tracked
    )
    hits = dict(run_all_collectors([first, second], [], options))
    reset_config()
    return {"calls": calls, "hits": len(hits["long-line"])}


def test_warm_clean_head_skips_parse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert _warm_parse_skip_contract(tmp_path, monkeypatch) == {
        "calls": [],
        "hits": 2,
    }


def test_no_index_disables_store_reads(monkeypatch: pytest.MonkeyPatch) -> None:
    from slopgate.lint._collector_groups.run_options import collector_options_from_env

    monkeypatch.setenv(LINT_ENV_NO_INDEX, LINT_ENV_TRUE)
    options = collector_options_from_env()
    assert (
        options.use_index,
        options.persist_index,
        IncrementalContext.__name__,
        dirty_relatives.__name__,
    ) == (False, False, "IncrementalContext", "dirty_relatives")


def test_cli_flags_clear_preexisting_lint_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from slopgate.cli.lint.scan_flags import (
        LintScanFlags,
        apply_lint_scan_env,
        restore_lint_scan_env,
    )
    from slopgate.lint._collector_groups.run_options import collector_options_from_env
    import os

    monkeypatch.setenv(LINT_ENV_PROFILE, LINT_ENV_TRUE)
    prior = apply_lint_scan_env(LintScanFlags())
    options = collector_options_from_env()
    restore_lint_scan_env(prior)
    assert {
        "profile": options.profile,
        "restored": os.environ.get(LINT_ENV_PROFILE),
    } == {"profile": None, "restored": LINT_ENV_TRUE}
