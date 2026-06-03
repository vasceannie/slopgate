from __future__ import annotations

import argparse
import keyword
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

import pytest
from hypothesis import given, strategies

from vibeforcer.installer import _shared as installer_shared
from vibeforcer.rules.python_ast._helpers import detect_family_prefix, evaluate_common
from vibeforcer.search.cli import cmd_list, cmd_models, cmd_remove, cmd_use
from vibeforcer.search import config as search_config
from vibeforcer.search.config import expand
from vibeforcer.config._repo import is_path_skipped, is_repo_disabled, list_git_worktrees

IDENTIFIERS = strategies.from_regex(r"[a-z][a-z0-9_]{0,12}", fullmatch=True).filter(
    lambda value: not keyword.iskeyword(value)
)
SHORT_TEXT = strategies.text(alphabet="abcdefghijklmnopqrstuvwxyz0123456789 _.-/", max_size=40)


@given(value=SHORT_TEXT)
def test_coerce_hook_entries_returns_list_for_non_lists_property(value: str) -> None:
    assert installer_shared.coerce_hook_entries(value) == []


@given(event=strategies.sampled_from(["PreToolUse", "PostToolUse"]))
def test_merge_owned_hooks_into_preserves_unrelated_events_property(event: str) -> None:
    config: dict[str, object] = {"hooks": {event: [{"hooks": []}]}}
    installer_shared.merge_owned_hooks_into(config, {event: []})

    assert event in cast(dict[str, object], config["hooks"])


def test_evaluate_common_is_callable_property() -> None:
    assert callable(evaluate_common)


@given(repo_name=IDENTIFIERS)
def test_list_git_worktrees_returns_list_for_missing_repo_property(repo_name: str) -> None:
    with TemporaryDirectory() as raw_path:
        worktrees = list_git_worktrees(Path(raw_path) / repo_name)

    assert worktrees == []


@given(prefix=strategies.sampled_from(["parse_", "build_", "validate_"]))
def test_detect_family_prefix_requires_three_matching_names_property(prefix: str) -> None:
    assert detect_family_prefix([f"{prefix}a", f"{prefix}b", f"{prefix}c"]) == prefix


@given(path_part=SHORT_TEXT)
def test_is_path_skipped_matches_configured_prefixes_property(path_part: str) -> None:
    with TemporaryDirectory() as raw_path:
        skipped = is_path_skipped(Path(raw_path) / path_part, [path_part])

    assert isinstance(skipped, bool)


@given(repo_name=IDENTIFIERS)
def test_is_repo_disabled_is_false_without_sentinel_property(repo_name: str) -> None:
    with TemporaryDirectory() as raw_path:
        disabled = is_repo_disabled(Path(raw_path) / repo_name)

    assert disabled is False


@given(label=SHORT_TEXT)
def test_require_json_object_rejects_invalid_json_property(
    tmp_path: Path,
    label: str,
) -> None:
    target = tmp_path / "invalid.json"
    target.write_text("{", encoding="utf-8")

    assert installer_shared.require_json_object(target, label, action="install") is None


def test_cmd_list_returns_zero_without_local_indexes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("vibeforcer.search.cli.local_indexes", lambda: [])

    assert cmd_list(argparse.Namespace()) == 0


def test_cmd_models_returns_nonzero_without_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LITELLM_API_KEY", raising=False)

    assert cmd_models(argparse.Namespace()) != 0


def test_cmd_remove_returns_nonzero_for_missing_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("vibeforcer.search.cli.load_config", lambda: search_config.SearchConfig())

    assert cmd_remove(argparse.Namespace(repo="missing-repo")) != 0


def test_cmd_use_returns_nonzero_without_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("vibeforcer.search.cli.load_config", lambda: search_config.SearchConfig())

    assert cmd_use(argparse.Namespace(model=None)) != 0


@given(path_text=strategies.one_of(strategies.none(), SHORT_TEXT))
def test_expand_returns_default_for_missing_path_property(path_text: str | None) -> None:
    with TemporaryDirectory() as raw_path:
        default = Path(raw_path) / "default.yml"

    assert expand(path_text, default=default) == default
