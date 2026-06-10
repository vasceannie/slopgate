from __future__ import annotations

import json
from pathlib import Path
from typing import Self

import pytest

from slopgate.search import config
from slopgate.search import runtime
from slopgate.search.config import SearchConfig


class ModelResponse:
    def __init__(self, model_ids: list[str]) -> None:
        payload = {"data": [{"id": model_id} for model_id in model_ids]}
        self._raw = json.dumps(payload).encode("utf-8")

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return self._raw


def test_fetch_models_reads_openai_compatible_model_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    def fake_urlopen(request: object, timeout: int) -> ModelResponse:
        seen["request"] = request
        seen["timeout"] = timeout
        return ModelResponse(["ignored-chat", "text-embedding-3-small"])

    monkeypatch.setattr(runtime.urllib.request, "urlopen", fake_urlopen)

    models = runtime.fetch_models("https://llm.example/", "secret", timeout=3)

    assert {"models": models, "timeout": seen["timeout"]} == {
        "models": ["ignored-chat", "text-embedding-3-small"],
        "timeout": 3,
    }


def test_choose_litellm_model_prefers_discovered_embedding_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LITELLM_API_KEY", "secret")

    def fake_fetch_models(base_url: str, api_key: str) -> list[str]:
        _ = base_url, api_key
        return ["chat", "text-embedding-3-small"]

    monkeypatch.setattr(runtime, "fetch_models", fake_fetch_models)

    choice = runtime.choose_litellm_model(
        "https://llm.example",
        "LITELLM_API_KEY",
        explicit_model=None,
    )

    assert choice == (
        "text-embedding-3-small",
        ["chat", "text-embedding-3-small"],
        None,
    )


def test_choose_litellm_model_uses_explicit_and_default_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MISSING_LITELLM_KEY", raising=False)

    explicit = runtime.choose_litellm_model("https://llm.example", None, "custom/model")
    fallback = runtime.choose_litellm_model(
        "https://llm.example",
        "MISSING_LITELLM_KEY",
        explicit_model=None,
    )

    assert {
        "explicit": explicit,
        "fallback_model": fallback[0],
        "fallback_models": fallback[1],
    } == {
        "explicit": ("custom/model", None, None),
        "fallback_model": "ollama/nomic-embed-text",
        "fallback_models": None,
    }


def test_embedding_like_identifies_embedding_model_names() -> None:
    assert {
        "preferred": runtime.embedding_like("text-embedding-3-small"),
        "ollama": runtime.embedding_like("ollama/my-embedding-model"),
        "chat": runtime.embedding_like("gpt-4o"),
    } == {"preferred": True, "ollama": True, "chat": False}


def test_render_and_write_islands_yaml_include_model_and_paths(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "islands.yml"

    yaml_text = runtime.render_islands_yaml("text-embedding-3-small")
    runtime.write_islands_config(target, "text-embedding-3-small")

    assert {
        "rendered_model": "model: text-embedding-3-small" in yaml_text,
        "written_model": "model: text-embedding-3-small" in target.read_text(),
        "written_exists": target.exists(),
    } == {
        "rendered_model": True,
        "written_model": True,
        "written_exists": True,
    }


def test_runtime_env_merges_configured_api_and_extra_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CUSTOM_API_KEY", "from-env")
    cfg = SearchConfig(
        base_url="https://llm.example",
        api_key_env="CUSTOM_API_KEY",
    )

    env = runtime.runtime_env(cfg, extra_env={"EXTRA": "value"})

    assert {
        "base": env["OPENAI_BASE_URL"],
        "key": env["OPENAI_API_KEY"],
        "extra": env["EXTRA"],
    } == {
        "base": "https://llm.example",
        "key": "from-env",
        "extra": "value",
    }


def test_runtime_env_rejects_missing_required_api_key() -> None:
    cfg = SearchConfig(api_key_env="MISSING_RUNTIME_KEY")

    with pytest.raises(config.IsxError, match="required env var"):
        runtime.runtime_env(cfg)


def test_islands_binary_and_config_path_resolve_config_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_which(binary: str) -> str:
        return f"/bin/{binary}"

    monkeypatch.setattr(runtime.shutil, "which", fake_which)
    cfg = SearchConfig(binary="islands", islands_config=str(tmp_path / "islands.yml"))

    resolved = {
        "binary": runtime.islands_binary(cfg),
        "config_path": runtime.current_islands_config_path(cfg),
    }

    assert resolved == {
        "binary": "/bin/islands",
        "config_path": tmp_path / "islands.yml",
    }


def test_save_runtime_model_persists_config_and_islands_yaml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved: dict[str, SearchConfig] = {}
    cfg = SearchConfig(islands_config=str(tmp_path / "islands.yml"))

    def fake_save_config(value: SearchConfig) -> None:
        saved["cfg"] = dict(value)

    monkeypatch.setattr(config, "save_config", fake_save_config)

    runtime.save_runtime_model(cfg, "text-embedding-3-small")

    assert {
        "model": cfg["model"],
        "saved_model": saved["cfg"]["model"],
        "yaml_has_model": "model: text-embedding-3-small"
        in (tmp_path / "islands.yml").read_text(),
    } == {
        "model": "text-embedding-3-small",
        "saved_model": "text-embedding-3-small",
        "yaml_has_model": True,
    }


def test_fetch_runtime_models_uses_runtime_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("RUNTIME_API_KEY", "secret")

    def fake_fetch_models(base_url: str, api_key: str) -> list[str]:
        return [f"{base_url}:{api_key}"]

    monkeypatch.setattr(runtime, "fetch_models", fake_fetch_models)
    cfg = SearchConfig(base_url="https://llm.example", api_key_env="RUNTIME_API_KEY")

    models = runtime.fetch_runtime_models(cfg)

    assert models == ["https://llm.example:secret"]


def test_run_islands_executes_resolved_binary_and_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, list[str] | dict[str, str]] = {}

    class Completed:
        returncode = 7

    def fake_run(command: list[str], env: dict[str, str]) -> Completed:
        calls["command"] = command
        calls["env"] = env
        return Completed()

    def fake_which(binary: str) -> str:
        return f"/bin/{binary}"

    monkeypatch.setattr(runtime.shutil, "which", fake_which)
    monkeypatch.setattr(runtime.subprocess, "run", fake_run)
    cfg = SearchConfig(binary="islands", islands_config=str(tmp_path / "islands.yml"))

    returncode = runtime.run_islands(cfg, ["doctor"], extra_env={"EXTRA": "value"})

    env = calls["env"]
    assert isinstance(env, dict)
    assert {
        "returncode": returncode,
        "command": calls["command"],
        "extra": env["EXTRA"],
    } == {
        "returncode": 7,
        "command": [
            "/bin/islands",
            "--config",
            str(tmp_path / "islands.yml"),
            "doctor",
        ],
        "extra": "value",
    }
