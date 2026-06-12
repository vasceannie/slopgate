from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from slopgate.search import cli
from slopgate.search.cli import doctor, init
from slopgate.search.cli.parser import build_search_parser
from slopgate.search.cli import (
    cmd_add,
    cmd_list,
    cmd_models,
    cmd_reindex,
    cmd_remove,
    cmd_search,
    cmd_sync,
    cmd_use,
)
from slopgate.search.config import SearchConfig
from tests.search_cli_support import (
    _capture_init_writes,
    _init_namespace_without_prompt,
    _stub_doctor_runtime,
)


def test_build_search_parser_registers_query_command() -> None:
    parser = build_search_parser()
    args = parser.parse_args(["query", "needle"])

    assert args.search_command == "query", f"Expected query, got {args.search_command}"
    assert args.query == ["needle"], f"Expected ['needle'], got {args.query}"
    assert callable(args.func), "Expected args.func to be callable"


def test_cmd_doctor_reports_config_and_runtime_status(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _stub_doctor_runtime(monkeypatch)

    assert doctor.cmd_doctor(argparse.Namespace()) == 0
    output = capsys.readouterr().out
    expected_markers = (
        "Provider:       litellm",
        "OPENAI_BASE_URL=set",
        "/v1/models:     ok (2 models)",
        "text-embedding-3-small",
        "ISX_TEST_KEY=set",
    )
    assert all(marker in output for marker in expected_markers)


def test_cmd_init_writes_config_and_islands_scaffold_without_prompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    islands_config = tmp_path / "islands.yaml"
    saved, islands_paths = _capture_init_writes(
        monkeypatch, tmp_path / "isx/config.json"
    )
    result = init.cmd_init(_init_namespace_without_prompt(islands_config))
    output = capsys.readouterr().out

    assert {
        "result": result,
        "provider": saved["provider"],
        "islands_config": saved["islands_config"],
        "islands_paths": islands_paths,
        "initialized": "Initialized isx." in output,
    } == {
        "result": 0,
        "provider": "ollama",
        "islands_config": str(islands_config),
        "islands_paths": [(islands_config, "nomic-embed-text")],
        "initialized": True,
    }


def _stub_load_config(monkeypatch: pytest.MonkeyPatch) -> SearchConfig:
    config: SearchConfig = {
        "binary": "islands-ollama",
        "provider": "ollama",
        "base_url": "http://localhost:11434",
        "model": "nomic-embed-text",
        "islands_config": "/tmp/islands.yaml",
    }

    def fake_load_config() -> SearchConfig:
        return config

    monkeypatch.setattr(cli, "load_config", fake_load_config)
    return config


def _stub_run_islands(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    calls: list[list[str]] = []

    def fake_run(
        cfg: SearchConfig,
        args: list[str],
        extra_env: dict[str, str] | None = None,
    ) -> int:
        _ = cfg, extra_env
        calls.append(args)
        return 0

    monkeypatch.setattr(cli, "run_islands", fake_run)
    return calls


def test_cmd_models_lists_embedding_models(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _stub_load_config(monkeypatch)

    def fake_fetch_runtime_models(_cfg: SearchConfig) -> list[str]:
        return ["nomic-embed-text", "gpt-4"]

    def fake_embedding_like(model: str) -> bool:
        return "embed" in model or "nomic" in model

    monkeypatch.setattr(cli, "fetch_runtime_models", fake_fetch_runtime_models)
    monkeypatch.setattr(cli, "embedding_like", fake_embedding_like)

    result = cmd_models(argparse.Namespace(all=False, json=False))
    output = capsys.readouterr().out

    assert result == 0
    assert "nomic-embed-text" in output


def _stub_model_update_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> list[dict[str, object]]:
    saved: list[dict[str, object]] = []

    def fake_fetch_runtime_models(_cfg: SearchConfig) -> list[str]:
        return ["nomic-embed-text"]

    def fake_save_runtime_model(cfg: SearchConfig, model: str) -> None:
        next_model = model.strip()
        previous_model = cfg.get("model")
        saved.append(
            {
                "previous": previous_model,
                "next": next_model,
                "changed": previous_model != next_model,
            }
        )

    def fake_current_islands_config_path(_cfg: SearchConfig) -> Path:
        raw_path = _cfg.get("islands_config")
        if not isinstance(raw_path, str) or not raw_path:
            raise AssertionError("Expected islands_config path in test config")
        return Path(raw_path)

    monkeypatch.setattr(cli, "fetch_runtime_models", fake_fetch_runtime_models)
    monkeypatch.setattr(cli, "save_runtime_model", fake_save_runtime_model)
    monkeypatch.setattr(
        cli, "current_islands_config_path", fake_current_islands_config_path
    )
    return saved


def test_cmd_use_updates_model(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _stub_load_config(monkeypatch)
    saved = _stub_model_update_runtime(monkeypatch)

    result = cmd_use(argparse.Namespace(model="nomic-embed-text", force=False))

    assert result == 0
    assert saved[0]["next"] == "nomic-embed-text"


def test_cmd_list_prints_no_indexes_message(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _stub_load_config(monkeypatch)

    def fake_local_indexes(_cfg: SearchConfig) -> list[object]:
        return []

    monkeypatch.setattr(cli, "local_indexes", fake_local_indexes)

    result = cmd_list(argparse.Namespace(json=False))
    output = capsys.readouterr().out

    assert result == 0
    assert "No local indexes" in output


def test_cmd_add_invokes_run_islands_with_add_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_load_config(monkeypatch)
    calls = _stub_run_islands(monkeypatch)

    def fake_resolve_add_repo(repo: str, cwd: Path | None = None) -> str:
        _ = cwd
        return repo

    def fake_resolve_token(
        args: argparse.Namespace,
        repo_url: str | None = None,
    ) -> tuple[str | None, dict[str, str]]:
        _ = args, repo_url
        return None, {}

    monkeypatch.setattr(cli, "resolve_add_repo", fake_resolve_add_repo)
    monkeypatch.setattr(cli, "_resolve_token", fake_resolve_token)

    result = cmd_add(
        argparse.Namespace(
            repo="https://github.com/example/repo.git",
            token="",
            token_env="",
        )
    )

    assert result == 0
    assert calls[0][0] == "add"


def test_cmd_search_invokes_run_islands_with_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_load_config(monkeypatch)
    calls = _stub_run_islands(monkeypatch)

    result = cmd_search(argparse.Namespace(query=["find", "auth", "flow"]))

    assert result == 0
    assert calls[0] == ["search", "find auth flow"]


def test_cmd_remove_raises_when_index_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from slopgate.search.config import IsxError

    _stub_load_config(monkeypatch)

    def fake_find_local_index(_cfg: SearchConfig, _name: str) -> None:
        return None

    monkeypatch.setattr(cli, "find_local_index", fake_find_local_index)

    with pytest.raises(IsxError, match="could not resolve"):
        cmd_remove(argparse.Namespace(target="nonexistent", force=False))


def test_cmd_sync_delegates_to_run_islands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_load_config(monkeypatch)
    calls = _stub_run_islands(monkeypatch)

    result = cmd_sync(argparse.Namespace(targets=["my-repo"]))

    assert result == 0
    assert calls[0] == ["sync", "my-repo"]


def test_cmd_reindex_adds_fresh_when_no_existing_index(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _stub_load_config(monkeypatch)
    _stub_run_islands(monkeypatch)

    def fake_resolve_reindex_target(
        cfg: SearchConfig,
        target: str,
        cwd: Path | None = None,
    ) -> tuple[str | None, str]:
        _ = cfg, target, cwd
        return None, "https://github.com/example/repo.git"

    def fake_resolve_token(
        args: argparse.Namespace,
        repo_url: str | None = None,
    ) -> tuple[str | None, dict[str, str]]:
        _ = args, repo_url
        return None, {}

    monkeypatch.setattr(cli, "resolve_reindex_target", fake_resolve_reindex_target)
    monkeypatch.setattr(cli, "_resolve_token", fake_resolve_token)

    result = cmd_reindex(
        argparse.Namespace(
            target="https://github.com/example/repo.git",
            token="",
            token_env="",
        )
    )
    output = capsys.readouterr().out

    assert result == 0
    assert "Adding repository" in output
