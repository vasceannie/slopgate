"""Implementation for ``isx doctor``."""

from __future__ import annotations

import argparse
import os
import urllib.error

from vibeforcer._types import string_value
from vibeforcer.search.config import APP_CONFIG, IsxError, SearchConfig, load_config
from vibeforcer.search.runtime import (
    embedding_like,
    fetch_runtime_models,
    islands_binary,
    runtime_env,
)


def _print_rows(rows: tuple[tuple[str, object], ...]) -> None:
    for label, value in rows:
        print(f"{label:<16}{value}")


def _print_doctor_config(cfg: SearchConfig) -> None:
    _print_rows(
        (
            ("CLI config:", APP_CONFIG),
            ("Islands config:", cfg.get("islands_config")),
            ("Binary:", cfg.get("binary")),
            ("Provider:", cfg.get("provider")),
            ("Base URL:", cfg.get("base_url")),
            ("Model:", cfg.get("model")),
            ("Integration:", cfg.get("integration", "none")),
        )
    )

    try:
        print(f"Binary path:    {islands_binary(cfg)}")
    except IsxError as exc:
        print(f"Binary path:    ERROR: {exc}")

    api_key_env = string_value(cfg.get("api_key_env"))
    if api_key_env:
        status = "set" if os.environ.get(api_key_env) else "missing"
        print(f"API key env:    {api_key_env}={status}")
    else:
        print("API key env:    n/a")


def _probe_doctor_endpoint(cfg: SearchConfig) -> int:
    try:
        env = runtime_env(cfg)
        base = "set" if env.get("OPENAI_BASE_URL") else "missing"
        key = "set" if env.get("OPENAI_API_KEY") else "missing"
        print(f"OPENAI_BASE_URL={base}")
        print(f"OPENAI_API_KEY={key}")
        models = fetch_runtime_models(cfg)
        print(f"/v1/models:     ok ({len(models)} models)")
        sample = [m for m in models if embedding_like(m)][:8]
        if sample:
            print("Embedding-ish routes:")
            for item in sample:
                print(f"  - {item}")
    except urllib.error.HTTPError as exc:
        print(f"/v1/models:     HTTP {exc.code}")
        return 1
    except (OSError, ValueError, IsxError) as exc:
        print(f"Runtime check:  ERROR: {exc}")
        return 1
    return 0


def cmd_doctor(_args: argparse.Namespace) -> int:
    cfg = load_config()
    _print_doctor_config(cfg)
    return _probe_doctor_endpoint(cfg)
