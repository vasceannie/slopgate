from __future__ import annotations

__all__ = [
    "Path",
    "doctor",
    "init",
    "SearchConfig",
    "_stub_doctor_runtime",
    "_capture_init_writes",
    "_init_namespace_without_prompt",
]


import argparse
from pathlib import Path

import pytest

from slopgate.search.cli import doctor, init
from slopgate.search.config import SearchConfig


def _stub_doctor_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    config: SearchConfig = {
        "islands_config": "/tmp/islands.yaml",
        "binary": "islands-ollama",
        "provider": "litellm",
        "base_url": "http://llm.local",
        "model": "embed-small",
        "integration": "none",
        "api_key_env": "ISX_TEST_KEY",
    }

    def fake_load_config() -> SearchConfig:
        return config

    def fake_islands_binary(_cfg: SearchConfig) -> Path:
        return Path("/bin/islands")

    def fake_runtime_env(_cfg: SearchConfig) -> dict[str, str]:
        return {"OPENAI_BASE_URL": "x", "OPENAI_API_KEY": "y"}

    def fake_fetch_runtime_models(_cfg: SearchConfig) -> list[str]:
        return ["text-embedding-3-small", "chat-model"]

    monkeypatch.setenv("ISX_TEST_KEY", "set-but-redacted")
    monkeypatch.setattr(doctor, "load_config", fake_load_config)
    monkeypatch.setattr(doctor, "islands_binary", fake_islands_binary)
    monkeypatch.setattr(doctor, "runtime_env", fake_runtime_env)
    monkeypatch.setattr(doctor, "fetch_runtime_models", fake_fetch_runtime_models)


def _capture_init_writes(
    monkeypatch: pytest.MonkeyPatch,
    app_config: Path,
) -> tuple[dict[str, object], list[tuple[Path, str]]]:
    saved: dict[str, object] = {}
    islands_paths: list[tuple[Path, str]] = []

    def fake_save_config(cfg: SearchConfig) -> None:
        saved.update(cfg)

    def fake_write_islands_config(path: Path, model: str) -> None:
        islands_paths.append((path, model))

    monkeypatch.setattr(init, "APP_CONFIG", app_config)
    monkeypatch.setattr(init, "save_config", fake_save_config)
    monkeypatch.setattr(init, "write_islands_config", fake_write_islands_config)
    return saved, islands_paths


def _init_namespace_without_prompt(islands_config: Path) -> argparse.Namespace:
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
