from __future__ import annotations

import json
from pathlib import Path

import pytest

from slopgate.search.config import (
    IsxError,
    detect_provider,
    expand,
    save_config,
)


def test_expand_resolves_explicit_path(tmp_path: Path) -> None:
    result = expand(str(tmp_path / "mydir"))

    assert result == (tmp_path / "mydir").resolve()


def test_expand_uses_default_when_path_is_none(tmp_path: Path) -> None:
    default = tmp_path / "default_dir"

    result = expand(None, default=default)

    assert result == default


def test_expand_uses_default_when_path_is_blank(tmp_path: Path) -> None:
    default = tmp_path / "default_dir"

    result = expand("  ", default=default)

    assert result == default


def test_expand_raises_isx_error_when_none_and_no_default() -> None:
    with pytest.raises(IsxError, match="missing path"):
        expand(None, default=None)


def test_save_config_writes_json_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import slopgate.search.config as config_mod

    app_dir = tmp_path / "isx"
    app_config = app_dir / "config.json"
    monkeypatch.setattr(config_mod, "APP_DIR", app_dir)
    monkeypatch.setattr(config_mod, "APP_CONFIG", app_config)

    data = {"provider": "ollama", "model": "nomic-embed-text"}
    save_config(data)

    written = json.loads(app_config.read_text(encoding="utf-8"))
    assert written == {"model": "nomic-embed-text", "provider": "ollama"}


def test_detect_provider_returns_litellm_when_env_var_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LITELLM_BASE_URL", "http://llm.local")
    monkeypatch.delenv("LITELLM_API_KEY", raising=False)

    result = detect_provider()

    assert result == "litellm"


def test_detect_provider_returns_ollama_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LITELLM_BASE_URL", raising=False)
    monkeypatch.delenv("LITELLM_API_KEY", raising=False)

    result = detect_provider()

    assert result == "ollama"


def test_detect_provider_returns_litellm_when_api_key_env_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LITELLM_BASE_URL", raising=False)
    monkeypatch.setenv("LITELLM_API_KEY", "sk-test-key")

    result = detect_provider()

    assert result == "litellm"
