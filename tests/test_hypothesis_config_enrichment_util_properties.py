from __future__ import annotations

import keyword
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from hypothesis import given, strategies

from slopgate.config._repo import enroll_repo
from slopgate.enrichment.fixtures import discover_fixtures, find_parametrize_examples
from slopgate.enrichment.pytest_enrichers import enrich_fixture_outside_conftest
from slopgate.rules.common._shell_read import is_safe_read_shell_command
from slopgate.search import runtime
from slopgate.search.runtime import (
    choose_litellm_model,
    embedding_like,
    fetch_models,
    fetch_runtime_models,
    runtime_env,
)
from slopgate.util.payloads._basic import is_edit_like_tool
from slopgate.util.payloads._shell import shell_command_paths
from slopgate.util.platform import normalize_path_for_match, resolve_path_for_match

_SHORT_TEXT = strategies.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789 _/-.",
    max_size=40,
)
IDENTIFIERS = strategies.from_regex(r"[a-z][a-z0-9_]{0,12}", fullmatch=True).filter(
    lambda value: not keyword.iskeyword(value)
)


@given(strategies.just(None))
def test_enrich_fixture_outside_conftest_is_callable_property(_: None) -> None:
    assert callable(enrich_fixture_outside_conftest)


@given(strategies.just(None))
def test_enroll_repo_returns_root_and_written_list_in_temp_dir_property(_: None) -> None:
    with TemporaryDirectory() as raw_path:
        root, written = enroll_repo(Path(raw_path), include_worktrees=False)
    assert isinstance(root, Path), "root must be a Path"
    assert isinstance(written, list), "written must be a list"


@given(strategies.text(alphabet="abcdefghijklmnopqrstuvwxyz-", max_size=30))
def test_embedding_like_returns_bool_property(model: str) -> None:
    result = embedding_like(model)
    assert isinstance(result, bool)


@given(strategies.just(None))
def test_choose_litellm_model_explicit_model_bypasses_discovery_property(_: None) -> None:
    model, models, _error = choose_litellm_model(
        "https://llm.example", None, "custom/model"
    )
    assert model == "custom/model"
    assert models is None


@given(strategies.just(None))
def test_fetch_models_is_callable_property(_: None) -> None:
    assert callable(fetch_models)


@given(strategies.just(None))
def test_fetch_runtime_models_uses_configured_api_key_property(_: None) -> None:
    from slopgate.search.config import SearchConfig

    with patch.dict(os.environ, {"RUNTIME_TEST_KEY": "test-secret"}):
        with patch.object(
            runtime,
            "fetch_models",
            lambda base_url, api_key: [f"{base_url}:{api_key}"],
        ):
            cfg = SearchConfig(base_url="https://llm.example", api_key_env="RUNTIME_TEST_KEY")
            models = fetch_runtime_models(cfg)

    assert models == ["https://llm.example:test-secret"]


@given(strategies.just(None))
def test_runtime_env_merges_api_key_from_configured_env_var_property(_: None) -> None:
    from slopgate.search.config import SearchConfig

    with patch.dict(os.environ, {"RUNTIME_ENV_TEST_KEY": "from-env"}):
        cfg = SearchConfig(
            base_url="https://llm.example",
            api_key_env="RUNTIME_ENV_TEST_KEY",
        )
        env = runtime_env(cfg)

    assert env["OPENAI_API_KEY"] == "from-env"
    assert env["OPENAI_BASE_URL"] == "https://llm.example"


@given(_SHORT_TEXT)
def test_shell_command_paths_returns_list_for_any_input_property(command: str) -> None:
    result = shell_command_paths(command)
    assert isinstance(result, list)


@given(IDENTIFIERS)
def test_is_edit_like_tool_returns_bool_for_any_name_property(name: str) -> None:
    result = is_edit_like_tool(name)
    assert isinstance(result, bool)


@given(_SHORT_TEXT)
def test_normalize_path_for_match_is_idempotent_property(value: str) -> None:
    once = normalize_path_for_match(value)
    twice = normalize_path_for_match(once)
    assert once == twice, "normalize_path_for_match must be idempotent"


@given(_SHORT_TEXT)
def test_resolve_path_for_match_returns_string_property(value: str) -> None:
    cwd = Path("/tmp")
    result = resolve_path_for_match(value, cwd)
    assert isinstance(result, str)


@given(strategies.just(None))
def test_discover_fixtures_returns_list_for_minimal_tree_property(_: None) -> None:
    with TemporaryDirectory() as raw_path:
        root = Path(raw_path)
        tests_dir = root / "tests"
        tests_dir.mkdir()
        test_file = tests_dir / "test_x.py"
        test_file.write_text("def test_x():\n    assert True\n", encoding="utf-8")
        fixtures = discover_fixtures(test_file, root)

    assert isinstance(fixtures, list)


@given(strategies.just(None))
def test_find_parametrize_examples_returns_list_for_minimal_tree_property(_: None) -> None:
    with TemporaryDirectory() as raw_path:
        root = Path(raw_path)
        tests_dir = root / "tests"
        tests_dir.mkdir()
        test_file = tests_dir / "test_x.py"
        test_file.write_text("def test_x():\n    assert True\n", encoding="utf-8")
        examples = find_parametrize_examples(test_file, root)

    assert isinstance(examples, list)


@given(_SHORT_TEXT)
def test_is_safe_read_shell_command_returns_bool_property(command: str) -> None:
    assert isinstance(is_safe_read_shell_command(command), bool)
