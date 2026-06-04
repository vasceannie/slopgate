from __future__ import annotations

import argparse
import ast
import io
import keyword
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

import pytest
from hypothesis import given, settings, strategies

from tests.test_enrichment_public_api import context_for_source
from slopgate.adapters.base import render_request_from_call
from slopgate.cli import commands as cli_commands
from slopgate.cli.main import main
from slopgate.config._repo import enroll_repo
from slopgate.enrichment.pytest_enrichers import enrich_fixture_outside_conftest
from slopgate.installer import _shared as installer_shared
from slopgate.installer import _suite as installer_suite
from slopgate.installer import _suite_autoupdate as suite_autoupdate
from slopgate.lint import _collectors
from slopgate.lint._detectors import code_smells, logging_conventions, stale_code, wrappers
from slopgate.lint._detectors.test_smells import _basic_detection
from slopgate.lint._helpers import ParsedFile, build_parent_map, compute_string_line_ranges
from slopgate.models import RuleFinding, Severity
from slopgate.rules.base import is_rule_enabled
from slopgate.search import config as search_config
from slopgate.search import runtime
from slopgate.util.payloads import _basic as payload_basic
from slopgate.util.payloads import _shell as payload_shell
from slopgate.util.platform import normalize_path_for_match, resolve_path_for_match

TEXT_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789 _.-/"
IDENTIFIERS = strategies.from_regex(r"[a-z][a-z0-9_]{0,12}", fullmatch=True).filter(
    lambda value: not keyword.iskeyword(value)
)
SHORT_TEXT = strategies.text(alphabet=TEXT_ALPHABET, max_size=40)
TOOL_NAMES = strategies.sampled_from(["Edit", "Write", "edit_file", "morph_edit", "Read"])


def _parsed(source: str, rel: str = "src/example.py") -> ParsedFile:
    tree = ast.parse(source)
    return ParsedFile(
        path=Path(rel),
        rel=rel,
        tree=tree,
        lines=source.splitlines(),
        parent_map=build_parent_map(tree),
        string_line_ranges=compute_string_line_ranges(tree),
    )


@given(name=IDENTIFIERS)
def test_enroll_repo_returns_tuple_for_missing_git_root_property(name: str) -> None:
    with TemporaryDirectory() as raw_path:
        root, written_roots = enroll_repo(Path(raw_path) / name, include_worktrees=False)

    assert isinstance(root, Path)
    assert isinstance(written_roots, list)
    assert all(isinstance(item, Path) for item in written_roots)


@given(rule_id=strategies.sampled_from(["FIXTURE-001", "PY-TEST-001"]), rel=SHORT_TEXT)
def test_enrich_fixture_outside_conftest_is_noop_without_path_property(
    rule_id: str,
    rel: str,
) -> None:
    with TemporaryDirectory() as raw_path:
        ctx = context_for_source(Path(raw_path), "value = 1\n")
        finding = RuleFinding(rule_id, "title", Severity.LOW, metadata={"hits": [rel]})
        enrich_fixture_outside_conftest(finding, ctx)

    assert finding.metadata["hits"] == [rel]


@given(
    base=strategies.sampled_from(["https://llm.example", "https://api.example/v1"]),
    explicit=strategies.one_of(strategies.none(), strategies.just("custom/model")),
)
def test_choose_litellm_model_honors_explicit_model_property(
    base: str,
    explicit: str | None,
) -> None:
    model, discovered, _ = runtime.choose_litellm_model(base, None, explicit_model=explicit)

    assert model == explicit if explicit is not None else model


@given(extra=strategies.dictionaries(strategies.text(min_size=1, max_size=8), SHORT_TEXT, max_size=2))
def test_runtime_env_merges_extra_env_property(extra: dict[str, str]) -> None:
    cfg = search_config.SearchConfig(base_url="https://llm.example", api_key_env="")
    env = runtime.runtime_env(cfg, extra_env=extra)

    assert all(env[key] == value for key, value in extra.items())


def test_main_returns_zero_for_version_flag() -> None:
    assert main(["--version"]) == 0


@settings(deadline=None)
@given(name=IDENTIFIERS)
def test_run_touched_collectors_returns_mapping_property(name: str) -> None:
    assert isinstance(_run_touched_collectors_sample(name), list)


@given(name=IDENTIFIERS)
def test_code_smell_detectors_accept_minimal_module_property(name: str) -> None:
    parsed = [_parsed(f"def {name}():\n    return 1\n")]

    assert (
        code_smells.detect_deep_nesting(parsed),
        code_smells.detect_high_complexity(parsed),
        code_smells.detect_long_methods(parsed),
        code_smells.detect_oversized_modules(parsed),
        code_smells.detect_too_many_params(parsed),
    ) == ([], [], [], [], [])


@given(name=IDENTIFIERS)
def test_logging_detectors_accept_minimal_module_property(name: str) -> None:
    source = "from slopgate.util.logger import make_logger\nlogger = make_logger(__name__)\n"
    parsed = [_parsed(source.replace("make_logger", name), rel="src/logging_sample.py")]

    assert (
        logging_conventions.detect_direct_get_logger(parsed),
        logging_conventions.detect_wrong_logger_name(parsed),
    ) == ([], [])


@given(name=IDENTIFIERS)
def test_detect_stale_patterns_accepts_clean_module_property(name: str) -> None:
    parsed = [_parsed(f"def {name}():\n    return 1\n")]

    assert stale_code.detect_stale_patterns(parsed) == []


@given(name=IDENTIFIERS)
def test_basic_test_smell_detectors_accept_valid_test_property(name: str) -> None:
    parsed = [_parsed(f"def test_{name}():\n    assert 1 == 1\n", rel="tests/test_sample.py")]

    assert (
        _basic_detection.detect_assertion_free_tests(parsed),
        _basic_detection.detect_eager_tests(parsed),
        _basic_detection.detect_long_tests(parsed),
    ) == ([], [], [])


@given(name=IDENTIFIERS)
def test_detect_unnecessary_wrappers_ignores_direct_logic_property(name: str) -> None:
    parsed = [_parsed(f"def {name}(value):\n    return value + 1\n")]

    assert wrappers.detect_unnecessary_wrappers(parsed) == []


@given(model_id=SHORT_TEXT.filter(lambda value: bool(value.strip())))
def test_fetch_models_parses_model_ids_property(model_id: str) -> None:
    class Response:
        def __enter__(self) -> Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            import json

            return json.dumps({"data": [{"id": model_id}]}).encode("utf-8")

    def fake_urlopen(_request: object, timeout: int) -> Response:
        assert timeout == 10
        return Response()

    import urllib.request

    original = urllib.request.urlopen
    urllib.request.urlopen = cast(object, fake_urlopen)
    try:
        models = runtime.fetch_models("https://llm.example", "secret")
    finally:
        urllib.request.urlopen = original

    assert models == [model_id]


@given(command=SHORT_TEXT)
def test_shell_command_paths_extracts_tokens_property(command: str) -> None:
    paths = payload_shell.shell_command_paths(command)

    assert isinstance(paths, list)


@given(platform=strategies.sampled_from(["claude", "codex", "opencode", "cursor"]))
def test_cmd_handle_accepts_empty_payload_property(platform: str) -> None:
    import sys

    original_stdin = sys.stdin
    sys.stdin = io.StringIO("")
    try:
        args = argparse.Namespace(platform=platform)
        assert cli_commands.cmd_handle(args) == 0
    finally:
        sys.stdin = original_stdin


@given(command=SHORT_TEXT)
def test_command_is_slopgate_hook_detects_handle_invocation_property(command: str) -> None:
    result = installer_shared.command_is_slopgate_hook(command)

    assert isinstance(result, bool)


def test_update_suite_returns_nonzero_when_package_update_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FailedRun:
        returncode = 1

    monkeypatch.setattr(installer_suite.subprocess, "run", lambda *_a, **_k: _FailedRun())

    assert installer_suite.update_suite(dry_run=False) == 1


def test_install_autoupdate_dry_run_allows_missing_binary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(suite_autoupdate, "is_windows", lambda: False)
    monkeypatch.setattr(suite_autoupdate.sys, "platform", "linux")
    monkeypatch.setattr(suite_autoupdate, "find_binary", lambda: "")

    assert suite_autoupdate.install_autoupdate(dry_run=True) == 0


def test_uninstall_autoupdate_is_noop_without_scheduler_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setattr(suite_autoupdate, "is_windows", lambda: False)
    monkeypatch.setattr(suite_autoupdate.sys, "platform", "linux")

    assert suite_autoupdate.uninstall_autoupdate(dry_run=True) == 0


def _write_sample_module(root: Path, name: str) -> Path:
    src_path = root / "src" / f"{name}.py"
    src_path.parent.mkdir(parents=True, exist_ok=True)
    src_path.write_text(f"def {name}():\n    return 1\n", encoding="utf-8")
    return src_path


def _run_touched_collectors_sample(name: str) -> list[tuple[str, list[object]]]:
    with TemporaryDirectory() as raw_path:
        src_path = _write_sample_module(Path(raw_path), name)
        return _collectors.run_touched_collectors(
            [src_path],
            [src_path],
            reference_test_files=[src_path],
        )


def _run_all_collectors_sample(name: str) -> list[tuple[str, list[object]]]:
    with TemporaryDirectory() as raw_path:
        src_path = _write_sample_module(Path(raw_path), name)
        return _collectors.run_all_collectors([src_path], [src_path])


def _run_test_integrity_collectors_sample(name: str) -> list[tuple[str, list[object]]]:
    with TemporaryDirectory() as raw_path:
        root = Path(raw_path)
        src_path = _write_sample_module(root, name)
        test_path = root / "tests" / f"test_{name}.py"
        test_path.parent.mkdir(parents=True, exist_ok=True)
        test_path.write_text(f"def test_{name}():\n    assert True\n", encoding="utf-8")
        return _collectors.run_test_integrity_collectors([src_path], [test_path])


@settings(deadline=None)
@given(name=IDENTIFIERS)
def test_run_all_collectors_returns_rule_mapping_property(name: str) -> None:
    assert isinstance(_run_all_collectors_sample(name), list)


@given(name=IDENTIFIERS)
def test_run_test_integrity_collectors_returns_rule_mapping_property(name: str) -> None:
    assert isinstance(_run_test_integrity_collectors_sample(name), list)


@given(model_name=SHORT_TEXT)
def test_embedding_like_is_boolean_property(model_name: str) -> None:
    assert isinstance(runtime.embedding_like(model_name), bool)


def test_fetch_runtime_models_returns_list_when_env_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RUNTIME_API_KEY", "secret")
    monkeypatch.setattr(runtime, "fetch_models", lambda _base, _key: ["model-a"])
    cfg = search_config.SearchConfig(base_url="https://llm.example", api_key_env="RUNTIME_API_KEY")

    assert runtime.fetch_runtime_models(cfg) == ["model-a"]


@given(tool=TOOL_NAMES)
def test_is_edit_like_tool_matches_edit_family_property(tool: str) -> None:
    assert isinstance(payload_basic.is_edit_like_tool(tool), bool)


@given(value=SHORT_TEXT)
def test_normalize_path_for_match_is_idempotent_property(value: str) -> None:
    once = normalize_path_for_match(value)
    twice = normalize_path_for_match(once)

    assert once == twice


@given(value=SHORT_TEXT)
def test_resolve_path_for_match_lowercases_relative_paths_property(value: str) -> None:
    with TemporaryDirectory() as raw_path:
        resolved = resolve_path_for_match(value, Path(raw_path))

    assert resolved == resolved.casefold()


def test_is_rule_enabled_is_callable_property() -> None:
    assert callable(is_rule_enabled)


@given(
    event=strategies.sampled_from(["PreToolUse", "PostToolUse", "stop"]),
    decision=strategies.one_of(strategies.none(), strategies.just("deny"), strategies.just("allow")),
)
def test_render_request_from_call_accepts_adapter_args_property(
    event: str,
    decision: str | None,
) -> None:
    kwargs: dict[str, object] = {}
    if decision is not None:
        kwargs["decision"] = decision
    request = render_request_from_call((event, []), kwargs)

    assert request.event_name == event
