from __future__ import annotations
import argparse
import keyword
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast
import pytest
from hypothesis import HealthCheck, given, settings, strategies
from slopgate.installer import _shared
from slopgate.cli._migrate import cmd_migrate
from slopgate.installer._install_scope import (
    InstallScope,
    ResidualInstallScopeWarning,
    normalize_install_scope,
    scope_paths,
    warn_residual_install_scope,
)
from slopgate.rules.python_ast._helpers import detect_family_prefix, evaluate_common
from slopgate.search.cli import cmd_list, cmd_models, cmd_remove, cmd_use
from slopgate.search import config
from slopgate.search.config import expand
from slopgate.config._repo import is_path_skipped, is_repo_disabled, list_git_worktrees

IDENTIFIERS = strategies.from_regex("[a-z][a-z0-9_]{0,12}", fullmatch=True).filter(
    lambda value: not keyword.iskeyword(value)
)
SHORT_TEXT = strategies.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789 _.-/", max_size=40
)


@given(value=SHORT_TEXT)
def test_coerce_hook_entries_returns_list_for_non_lists_property(value: str) -> None:
    assert _shared.coerce_hook_entries(value) == []


@given(event=strategies.sampled_from(["PreToolUse", "PostToolUse"]))
def test_merge_owned_hooks_into_preserves_unrelated_events_property(event: str) -> None:
    config: dict[str, object] = {"hooks": {event: [{"hooks": []}]}}
    _shared.merge_owned_hooks_into(config, {event: []})
    assert event in cast(dict[str, object], config["hooks"])


def test_evaluate_common_is_callable_property() -> None:
    assert callable(evaluate_common)


@given(repo_name=IDENTIFIERS)
def test_list_git_worktrees_returns_list_for_missing_repo_property(
    repo_name: str,
) -> None:
    with TemporaryDirectory() as raw_path:
        worktrees = list_git_worktrees(Path(raw_path) / repo_name)
    assert worktrees == []


@given(prefix=strategies.sampled_from(["parse_", "build_", "validate_"]))
def test_detect_family_prefix_requires_three_matching_names_property(
    prefix: str,
) -> None:
    assert detect_family_prefix([f"{prefix}a", f"{prefix}b", f"{prefix}c"]) == prefix


@given(path_part=SHORT_TEXT)
def test_is_path_skipped_matches_configured_prefixes_property(path_part: str) -> None:
    with TemporaryDirectory() as raw_path:
        skipped = is_path_skipped(Path(raw_path) / path_part, [path_part])
    assert isinstance(skipped, bool)


@given(scope=strategies.sampled_from(["user", "project", "both"]))
def test_normalize_install_scope_accepts_valid_scopes_property(scope: str) -> None:
    assert normalize_install_scope(scope) == scope


@given(
    scope=strategies.sampled_from(["user", "project", "both"]),
    user_suffix=IDENTIFIERS,
    project_suffix=IDENTIFIERS,
)
def test_scope_paths_returns_expected_targets_property(
    scope: InstallScope, user_suffix: str, project_suffix: str
) -> None:
    with TemporaryDirectory() as raw_path:
        root = Path(raw_path)
        user_path = root / f"user-{user_suffix}.json"
        project_path = root / f"project-{project_suffix}.json"
        expected: list[Path] = []
        if scope in {"user", "both"}:
            expected.append(user_path)
        if scope in {"project", "both"}:
            expected.append(project_path)
        assert (
            scope_paths(scope, user_path=user_path, project_path=project_path)
            == expected
        )


@given(repo_name=IDENTIFIERS)
def test_is_repo_disabled_is_false_without_sentinel_property(repo_name: str) -> None:
    with TemporaryDirectory() as raw_path:
        disabled = is_repo_disabled(Path(raw_path) / repo_name)
    assert disabled is False


@given(label=SHORT_TEXT)
def test_require_json_object_rejects_invalid_json_property(label: str) -> None:
    with TemporaryDirectory() as raw_path:
        target = Path(raw_path) / "invalid.json"
        target.write_text("{", encoding="utf-8")
        assert _shared.require_json_object(target, label, action="install") is None


def test_cmd_list_returns_zero_without_local_indexes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from slopgate.search import cli

    def fake_load_config() -> config.SearchConfig:
        return config.SearchConfig()

    def fake_local_indexes(_cfg: config.SearchConfig) -> list[object]:
        return []

    monkeypatch.setattr(cli, "load_config", fake_load_config)
    monkeypatch.setattr(cli, "local_indexes", fake_local_indexes)
    assert cmd_list(argparse.Namespace(json=False)) == 0


def test_cmd_models_returns_nonzero_without_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from slopgate.search import cli
    from slopgate.search.config import IsxError, SearchConfig

    config: SearchConfig = {
        "binary": "islands-ollama",
        "base_url": "http://localhost:11434",
        "api_key_env": "OPENAI_API_KEY",
    }
    monkeypatch.setattr(cli, "load_config", lambda: config)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LITELLM_API_KEY", raising=False)
    with pytest.raises(IsxError, match="required env var"):
        cmd_models(argparse.Namespace(all=False, json=False))


def test_cmd_remove_returns_nonzero_for_missing_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from slopgate.search import cli
    from slopgate.search.config import IsxError

    def fake_load_config() -> config.SearchConfig:
        return config.SearchConfig()

    def fake_find_local_index(_cfg: config.SearchConfig, _name: str) -> object | None:
        return None

    monkeypatch.setattr(cli, "load_config", fake_load_config)
    monkeypatch.setattr(cli, "find_local_index", fake_find_local_index)
    with pytest.raises(IsxError, match="could not resolve"):
        cmd_remove(argparse.Namespace(target="missing-repo", force=False))


def test_cmd_use_returns_nonzero_without_model(monkeypatch: pytest.MonkeyPatch) -> None:
    from slopgate.search import cli
    from slopgate.search.config import IsxError

    monkeypatch.setattr(cli, "load_config", lambda: config.SearchConfig())
    with pytest.raises(IsxError, match="model name is required"):
        cmd_use(argparse.Namespace(model=None, force=False))


@given(dry_run=strategies.booleans())
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_cmd_migrate_clean_repo_is_noop_property(tmp_path: Path, dry_run: bool) -> None:
    assert (
        cmd_migrate(
            argparse.Namespace(
                dry_run=dry_run,
                force=False,
                path=str(tmp_path),
                user_only=True,
                repo_only=True,
            )
        )
        == 0
    )


def _warn_residual_scope_output(
    tmp_path: Path, *, scope: str, platform_label: str, owned: Path
) -> str:
    user_path = tmp_path / "user.json"
    project_path = tmp_path / "project.json"
    user_path.write_text("{}", encoding="utf-8")
    project_path.write_text("{}", encoding="utf-8")
    warn_residual_install_scope(
        ResidualInstallScopeWarning(
            platform_label=platform_label,
            scope=scope,
            user_path=user_path,
            project_path=project_path,
            project_root=tmp_path,
            has_owned=lambda path: path == owned,
        )
    )
    return ""


@given(scope=strategies.sampled_from(["user", "project"]), platform_label=SHORT_TEXT)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_warn_residual_install_scope_prints_when_other_scope_owned_property(
    tmp_path: Path, scope: str, platform_label: str, capsys: pytest.CaptureFixture[str]
) -> None:
    owned = tmp_path / "user.json" if scope == "project" else tmp_path / "project.json"
    _warn_residual_scope_output(
        tmp_path, scope=scope, platform_label=platform_label, owned=owned
    )
    assert "remain at" in capsys.readouterr().out


@given(
    path_text=strategies.one_of(
        strategies.none(), strategies.text(alphabet=" \t", max_size=3)
    )
)
def test_expand_returns_default_for_missing_path_property(
    path_text: str | None,
) -> None:
    with TemporaryDirectory() as raw_path:
        default = Path(raw_path) / "default.yml"
        assert expand(path_text, default=default) == default
