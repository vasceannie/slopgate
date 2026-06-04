"""Implementation for ``isx init``."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from vibeforcer.search.config import (
    APP_CONFIG,
    APP_NAME,
    DEFAULT_ISLANDS_CONFIG,
    DEFAULT_OPENCODE_CONFIG,
    DEFAULT_OPENCODE_PLUGIN_PATH,
    DEFAULT_SKILL_NAME,
    IsxError,
    SearchConfig,
    detect_provider,
    expand,
    save_config,
)
from vibeforcer.search.runtime import (
    choose_litellm_model,
    embedding_like,
    write_islands_config,
)
from vibeforcer.search.scaffolds import scaffold_opencode_plugin, scaffold_skill


def _string_arg(args: argparse.Namespace, name: str, default: str = "") -> str:
    value = getattr(args, name, default)
    return value if isinstance(value, str) else default


def _bool_arg(args: argparse.Namespace, name: str, default: bool = False) -> bool:
    value = getattr(args, name, default)
    return value if isinstance(value, bool) else default


def _resolve_init_provider(args: argparse.Namespace) -> tuple[str, str]:
    provider = _string_arg(args, "provider") or detect_provider()
    base_url = _string_arg(args, "base_url")
    if base_url:
        return provider, base_url
    if provider == "litellm":
        return provider, os.environ.get("LITELLM_BASE_URL", "http://llm.toy")
    return provider, "http://localhost:11434"


def _resolve_litellm_model(
    args: argparse.Namespace,
    base_url: str,
) -> dict[str, str | list[str] | None]:
    api_key_env = _string_arg(args, "api_key_env") or "LITELLM_API_KEY"
    model, discovered, warning = choose_litellm_model(
        base_url,
        api_key_env,
        _string_arg(args, "model") or None,
    )
    return {
        "model": model,
        "api_key_env": api_key_env,
        "api_key_value": None,
        "discovered": discovered,
        "warning": warning,
    }


def _resolve_init_model(
    args: argparse.Namespace,
    provider: str,
    base_url: str,
) -> dict[str, str | list[str] | None]:
    if provider == "litellm":
        return _resolve_litellm_model(args, base_url)
    return {
        "model": _string_arg(args, "model") or "nomic-embed-text",
        "api_key_env": _string_arg(args, "api_key_env") or None,
        "api_key_value": _string_arg(args, "api_key_value") or "ollama",
        "discovered": None,
        "warning": None,
    }


def _guard_overwrite(islands_cfg: Path, force: bool) -> None:
    if APP_CONFIG.exists() and not force:
        raise IsxError(f"{APP_CONFIG} already exists. Re-run with --force to overwrite it.")
    if islands_cfg.exists() and not force:
        raise IsxError(f"{islands_cfg} already exists. Re-run with --force to overwrite it.")


def _scaffold_integration(
    integration: str,
    args: argparse.Namespace,
) -> tuple[list[Path], Path | None]:
    if integration == "skill":
        paths = scaffold_skill(
            _string_arg(args, "skill_name", DEFAULT_SKILL_NAME),
            _string_arg(args, "skill_target", "both"),
            force=_bool_arg(args, "force"),
        )
        return paths, None
    if integration == "opencode-tool":
        plugin = scaffold_opencode_plugin(
            expand(_string_arg(args, "opencode_plugin_path"), DEFAULT_OPENCODE_PLUGIN_PATH),
            expand(_string_arg(args, "opencode_config"), DEFAULT_OPENCODE_CONFIG),
            force=_bool_arg(args, "force"),
        )
        return [], plugin
    return [], None


def _print_rows(rows: tuple[tuple[str, object], ...]) -> None:
    for label, value in rows:
        print(f"  {label:<16}{value}")


def _print_init_summary(
    cli_cfg: SearchConfig,
    info: dict[str, str | list[str] | None],
) -> None:
    print(f"Initialized {APP_NAME}.")
    _print_rows(
        (
            ("CLI config:", APP_CONFIG),
            ("Islands config:", cli_cfg["islands_config"]),
            ("Provider:", cli_cfg["provider"]),
            ("Base URL:", cli_cfg["base_url"]),
            ("Model:", cli_cfg["model"]),
            ("Integration:", cli_cfg["integration"]),
        )
    )
    if info.get("api_key_env"):
        print(f"  API key env:    {info['api_key_env']}")
    elif info.get("api_key_value"):
        print("  API key:        stored as fixed runtime value")
    if info.get("warning"):
        print(f"  Note:           {info['warning']}")
    _print_discovered(info.get("discovered"))


def _print_discovered(discovered: str | list[str] | None) -> None:
    if not isinstance(discovered, list):
        return
    hits = [m for m in discovered if embedding_like(m)][:10]
    if not hits:
        return
    print("  Embedding routes seen:")
    for item in hits:
        print(f"    - {item}")


def _print_scaffold_results(
    skill_paths: list[Path],
    plugin_path: Path | None,
    args: argparse.Namespace,
) -> None:
    if skill_paths:
        print("  Skills written:")
        for path in skill_paths:
            print(f"    - {path}")
    if plugin_path:
        print(f"  OpenCode tool:  {plugin_path}")
        oc = expand(_string_arg(args, "opencode_config"), DEFAULT_OPENCODE_CONFIG)
        print(f"  OpenCode config:{oc}")


def _prompt_integration_choice() -> str:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        return "none"
    print("Integration setup:")
    for option in (
        "  1) none",
        "  2) skill (Claude Code / OpenCode)",
        "  3) opencode-tool (native OpenCode plugin)",
    ):
        print(option)
    choice = input("Select integration [1]: ").strip() or "1"
    return {"1": "none", "2": "skill", "3": "opencode-tool"}.get(choice, "none")


def _print_next_steps() -> None:
    for command in (
        "doctor",
        "models",
        "add https://github.com/panbanda/islands",
        'search "embedding model configuration"',
    ):
        print(f"  {APP_NAME} {command}")


def cmd_init(args: argparse.Namespace) -> int:
    integration = _string_arg(args, "integration") or _prompt_integration_choice()
    provider, base_url = _resolve_init_provider(args)
    info = _resolve_init_model(args, provider, base_url)
    model = str(info["model"])
    islands_cfg = expand(_string_arg(args, "islands_config"), DEFAULT_ISLANDS_CONFIG)
    _guard_overwrite(islands_cfg, _bool_arg(args, "force"))

    cli_cfg: SearchConfig = {
        "provider": provider,
        "binary": _string_arg(args, "binary", "islands-ollama"),
        "base_url": base_url,
        "api_key_env": info["api_key_env"],
        "api_key_value": info["api_key_value"],
        "model": model,
        "islands_config": str(islands_cfg),
        "integration": integration,
    }
    save_config(cli_cfg)
    write_islands_config(islands_cfg, model)

    skill_paths, plugin_path = _scaffold_integration(integration, args)
    _print_init_summary(cli_cfg, info)
    _print_scaffold_results(skill_paths, plugin_path, args)
    print("\nTry:")
    _print_next_steps()
    return 0
