from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from vibeforcer.search import _cli_doctor, _cli_init
from vibeforcer.search._cli_parser import build_search_parser


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
