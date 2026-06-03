from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from vibeforcer.search import _cli_doctor, _cli_init
from vibeforcer.search._cli_parser import build_search_parser
from vibeforcer.search.cli import (
    cmd_add,
    cmd_list,
    cmd_models,
    cmd_reindex,
    cmd_remove,
    cmd_search,
    cmd_sync,
    cmd_use,
)


def test_build_search_parser_registers_query_command() -> None:
    parser = build_search_parser()
    args = parser.parse_args(["query", "needle"])

    assert args.search_command == "query"
    assert args.query == ["needle"]
    assert callable(args.func)


def _stub_doctor_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    config = {
        "islands_config": "/tmp/islands.yaml",
        "binary": "islands-ollama",
        "provider": "litellm",
        "base_url": "http://llm.local",
        "model": "embed-small",
        "integration": "none",
        "api_key_env": "ISX_TEST_KEY",
    }
    monkeypatch.setenv("ISX_TEST_KEY", "set-but-redacted")
    monkeypatch.setattr(_cli_doctor, "load_config", lambda: config)
    monkeypatch.setattr(_cli_doctor, "islands_binary", lambda _cfg: Path("/bin/islands"))
    monkeypatch.setattr(
        _cli_doctor,
        "runtime_env",
        lambda _cfg: {"OPENAI_BASE_URL": "x", "OPENAI_API_KEY": "y"},
    )
    monkeypatch.setattr(
        _cli_doctor,
        "fetch_runtime_models",
        lambda _cfg: ["text-embedding-3-small", "chat-model"],
    )


def test_cmd_doctor_reports_config_and_runtime_status(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _stub_doctor_runtime(monkeypatch)

    assert _cli_doctor.cmd_doctor(argparse.Namespace()) == 0
    output = capsys.readouterr().out
    expected_markers = (
        "Provider:       litellm",
        "OPENAI_BASE_URL=set",
        "/v1/models:     ok (2 models)",
        "text-embedding-3-small",
        "ISX_TEST_KEY=set",
    )
    assert all(marker in output for marker in expected_markers)


def _init_args(islands_config: Path) -> argparse.Namespace:
    return argparse.Namespace(
        provider="ollama",
        base_url="http://localhost:11434",
        model="nomic-embed-text",
        api_key_env=None,
        api_key_value=None,
        binary="islands-ollama",
        islands_config=str(islands_config),
        integration="none",
        skill_name="isx-search",
        skill_target="both",
        opencode_plugin_path=None,
        opencode_config=None,
        force=False,
    )


def _capture_init_writes(
    monkeypatch: pytest.MonkeyPatch,
    app_config: Path,
) -> tuple[dict[str, object], list[tuple[Path, str]]]:
    saved: dict[str, object] = {}
    islands_paths: list[tuple[Path, str]] = []
    monkeypatch.setattr(_cli_init, "APP_CONFIG", app_config)
    monkeypatch.setattr(_cli_init, "save_config", lambda cfg: saved.update(cfg))
    monkeypatch.setattr(
        _cli_init,
        "write_islands_config",
        lambda path, model: islands_paths.append((path, model)),
    )
    return saved, islands_paths


def test_cmd_init_writes_config_and_islands_scaffold_without_prompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    islands_config = tmp_path / "islands.yaml"
    saved, islands_paths = _capture_init_writes(monkeypatch, tmp_path / "isx/config.json")
    result = _cli_init.cmd_init(_init_args(islands_config))
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


def _stub_load_config(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    from vibeforcer.search import cli as search_cli

    config: dict[str, object] = {
        "binary": "islands-ollama",
        "provider": "ollama",
        "base_url": "http://localhost:11434",
        "model": "nomic-embed-text",
    }
    monkeypatch.setattr(search_cli, "load_config", lambda: config)
    return config


def _stub_run_islands(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    from vibeforcer.search import cli as search_cli

    calls: list[list[str]] = []

    def fake_run(cfg: object, args: list[str], extra_env: dict[str, str] | None = None) -> int:
        calls.append(args)
        return 0

    monkeypatch.setattr(search_cli, "run_islands", fake_run)
    return calls


def test_cmd_models_lists_embedding_models(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from vibeforcer.search import cli as search_cli

    _stub_load_config(monkeypatch)
    monkeypatch.setattr(
        search_cli,
        "fetch_runtime_models",
        lambda _cfg: ["nomic-embed-text", "gpt-4"],
    )
    monkeypatch.setattr(search_cli, "embedding_like", lambda m: "embed" in m or "nomic" in m)

    result = cmd_models(argparse.Namespace(all=False, json=False))
    output = capsys.readouterr().out

    assert result == 0
    assert "nomic-embed-text" in output


def test_cmd_use_updates_model(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from vibeforcer.search import cli as search_cli

    _stub_load_config(monkeypatch)
    monkeypatch.setattr(search_cli, "fetch_runtime_models", lambda _cfg: ["nomic-embed-text"])
    saved: list[tuple[object, str]] = []
    monkeypatch.setattr(search_cli, "save_runtime_model", lambda cfg, m: saved.append((cfg, m)))
    monkeypatch.setattr(search_cli, "current_islands_config_path", lambda _cfg: Path("/tmp/islands.yaml"))

    result = cmd_use(argparse.Namespace(model="nomic-embed-text", force=False))

    assert result == 0
    assert saved[0][1] == "nomic-embed-text"


def test_cmd_list_prints_no_indexes_message(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from vibeforcer.search import cli as search_cli

    _stub_load_config(monkeypatch)
    monkeypatch.setattr(search_cli, "local_indexes", lambda _cfg: [])

    result = cmd_list(argparse.Namespace(json=False))
    output = capsys.readouterr().out

    assert result == 0
    assert "No local indexes" in output


def test_cmd_add_invokes_run_islands_with_add_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vibeforcer.search import cli as search_cli

    _stub_load_config(monkeypatch)
    calls = _stub_run_islands(monkeypatch)
    monkeypatch.setattr(search_cli, "resolve_add_repo", lambda repo, cwd=None: repo)
    monkeypatch.setattr(search_cli, "_resolve_token", lambda args, repo_url=None: (None, {}))

    result = cmd_add(argparse.Namespace(
        repo="https://github.com/example/repo.git",
        token="",
        token_env="",
    ))

    assert result == 0
    assert calls[0][0] == "add"


def test_cmd_search_invokes_run_islands_with_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vibeforcer.search import cli as search_cli

    _stub_load_config(monkeypatch)
    calls = _stub_run_islands(monkeypatch)

    result = cmd_search(argparse.Namespace(query=["find", "auth", "flow"]))

    assert result == 0
    assert calls[0] == ["search", "find auth flow"]


def test_cmd_remove_raises_when_index_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vibeforcer.search import cli as search_cli
    from vibeforcer.search.config import IsxError

    _stub_load_config(monkeypatch)
    monkeypatch.setattr(search_cli, "find_local_index", lambda _cfg, _name: None)

    with pytest.raises(IsxError, match="could not resolve"):
        cmd_remove(argparse.Namespace(target="nonexistent", force=False))


def test_cmd_sync_delegates_to_run_islands(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from vibeforcer.search import cli as search_cli

    _stub_load_config(monkeypatch)
    calls = _stub_run_islands(monkeypatch)

    result = cmd_sync(argparse.Namespace(targets=["my-repo"]))

    assert result == 0
    assert calls[0] == ["sync", "my-repo"]


def test_cmd_reindex_adds_fresh_when_no_existing_index(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from vibeforcer.search import cli as search_cli

    _stub_load_config(monkeypatch)
    calls = _stub_run_islands(monkeypatch)
    monkeypatch.setattr(
        search_cli,
        "resolve_reindex_target",
        lambda cfg, target, cwd=None: (None, "https://github.com/example/repo.git"),
    )
    monkeypatch.setattr(search_cli, "_resolve_token", lambda args, repo_url=None: (None, {}))

    result = cmd_reindex(argparse.Namespace(
        target="https://github.com/example/repo.git",
        token="",
        token_env="",
    ))
    output = capsys.readouterr().out

    assert result == 0
    assert "Adding repository" in output
