"""CLI subcommands for slopgate search (isx integration)."""

from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
from typing import cast
from slopgate._argparse_types import SubparserRegistry
from slopgate._types import object_dict
from urllib.parse import urlparse, urlunparse
from slopgate.search.completions import print_completion
from slopgate.search.config import APP_NAME, IsxError, SearchConfig, load_config
from slopgate.search.git_utils import resolve_add_repo
from slopgate.search.index_ops import (
    find_local_index,
    local_indexes,
    resolve_reindex_target,
)
from slopgate.search.runtime import (
    current_islands_config_path,
    embedding_like,
    fetch_runtime_models,
    run_islands,
    save_runtime_model,
)


def string_arg(args: argparse.Namespace, name: str, default: str = "") -> str:
    value = getattr(args, name, default)
    return value if isinstance(value, str) else default


def _bool_arg(args: argparse.Namespace, name: str, default: bool = False) -> bool:
    value = getattr(args, name, default)
    return value if isinstance(value, bool) else default


def _string_list_arg(args: argparse.Namespace, name: str) -> list[str]:
    raw_value = getattr(args, name, None)
    if not isinstance(raw_value, list):
        return []
    return [item for item in cast(list[object], raw_value) if isinstance(item, str)]


def _token_from_cli(args: argparse.Namespace) -> tuple[str | None, dict[str, str]]:
    """Check ``--token`` and ``--token-env`` flags."""
    extra: dict[str, str] = {}
    token = string_arg(args, "token")
    if token:
        extra["ISLANDS_GIT_TOKEN"] = token
        return ("--token", extra)
    token_env = string_arg(args, "token_env")
    if not token_env:
        return (None, extra)
    value = os.environ.get(token_env)
    if not value:
        raise IsxError(
            f"environment variable {token_env} is not set. "
            + "Set it or use --token <value> instead."
        )
    extra["ISLANDS_GIT_TOKEN"] = value
    return (token_env, extra)


def _token_from_config(repo_url: str | None) -> str | None:
    """Check isx config for a saved token matching the repo host."""
    if not repo_url or not repo_url.startswith("https://"):
        return None
    try:
        cfg = load_config()
    except IsxError:
        return None
    git_tokens = cfg.get("git_tokens", {})
    if not isinstance(git_tokens, dict):
        return None
    host = urlparse(repo_url).hostname or ""
    token = git_tokens.get(host)
    return token if isinstance(token, str) and token else None


def _resolve_token(
    args: argparse.Namespace, repo_url: str | None = None
) -> tuple[str | None, dict[str, str]]:
    """Resolve a git token from CLI flags, config, or env."""
    source, extra = _token_from_cli(args)
    if source:
        return (source, extra)
    config_token = _token_from_config(repo_url)
    if config_token:
        host = urlparse(repo_url or "").hostname or ""
        extra["ISLANDS_GIT_TOKEN"] = config_token
        return (f"config:{host}", extra)
    env_val = os.environ.get("ISLANDS_GIT_TOKEN")
    if env_val:
        extra["ISLANDS_GIT_TOKEN"] = env_val
        return ("ISLANDS_GIT_TOKEN", extra)
    return (None, extra)


def _embed_token_in_url(url: str, token: str) -> str:
    """Rewrite an HTTPS clone URL to embed *token* for auth."""
    if not url.startswith("https://"):
        return url
    parsed = urlparse(url)
    authed = parsed._replace(netloc=f"oauth2:{token}@{parsed.hostname}")
    return urlunparse(authed)


def _build_add_args(repo: str, extra: dict[str, str]) -> list[str]:
    """Build islands ``add`` args, optionally rewriting the URL."""
    add_args = ["add"]
    token_val = extra.get("ISLANDS_GIT_TOKEN")
    if token_val:
        add_args.extend(["--token", token_val])
        repo = _embed_token_in_url(repo, token_val)
    add_args.append(repo)
    return add_args


def cmd_init(args: argparse.Namespace) -> int:
    """Write wrapper and islands configs."""
    from slopgate.search._cli_init import cmd_init

    return cmd_init(args)


def cmd_doctor(args: argparse.Namespace) -> int:
    """Check runtime config and endpoint reachability."""
    from slopgate.search._cli_doctor import cmd_doctor

    return cmd_doctor(args)


def cmd_models(args: argparse.Namespace) -> int:
    """List available models from the configured endpoint."""
    cfg = load_config()
    models = fetch_runtime_models(cfg)
    current = cfg.get("model")
    shown = (
        models if _bool_arg(args, "all") else [m for m in models if embedding_like(m)]
    )
    if _bool_arg(args, "json"):
        print(json.dumps({"current": current, "models": shown}, indent=2))
        return 0
    if not shown:
        raise IsxError("no models matched the current filter")
    print(f"Current model: {current}")
    for model in shown:
        marker = "*" if model == current else " "
        print(f"{marker} {model}")
    return 0


def cmd_use(args: argparse.Namespace) -> int:
    """Switch to a different embedding model."""
    cfg = load_config()
    model = string_arg(args, "model").strip()
    if not model:
        raise IsxError("model name is required")
    if not _bool_arg(args, "force"):
        models = fetch_runtime_models(cfg)
        if model not in models:
            raise IsxError(
                f"model not found in /v1/models: {model}. "
                + "Run `isx models --all` to inspect available routes."
            )
    save_runtime_model(cfg, model)
    print(f"Updated model to {model}")
    print(f"Wrote {current_islands_config_path(cfg)}")
    print(
        "Note: if your existing indexes were built with a different "
        + "embedding dimension, re-add or rebuild them before searching."
    )
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """List locally known indexes."""
    cfg = load_config()
    items = local_indexes(cfg)
    if _bool_arg(args, "json"):
        print(json.dumps(items, indent=2))
        return 0
    if not items:
        print("No local indexes found.")
        print(f"Try: {APP_NAME} add https://github.com/panbanda/islands")
        return 0
    print(f"Local indexes ({len(items)}):")
    for item in items:
        repo = object_dict(item.get("repository"))
        print(f"- {item.get('name')}")
        print(f"  clone:   {repo.get('clone_url', 'unknown')}")
        print(f"  files:   {item.get('file_count', 0)}")
        print(f"  updated: {item.get('updated_at', 'unknown')}")
    return 0


def _run_add_repository(
    args: argparse.Namespace, repo_url: str, *, cfg: SearchConfig
) -> int:
    token_source, extra = _resolve_token(args, repo_url=repo_url)
    if token_source:
        print(f"Using token from {token_source} for repository access", flush=True)
    add_args = _build_add_args(repo_url, extra)
    return run_islands(cfg, add_args, extra_env=extra)


def cmd_add(args: argparse.Namespace) -> int:
    """Index a repository URL."""
    cfg = load_config()
    repo = resolve_add_repo(string_arg(args, "repo"), cwd=Path.cwd())
    return _run_add_repository(args, repo, cfg=cfg)


def cmd_search(args: argparse.Namespace) -> int:
    """Search indexed repositories."""
    cfg = load_config()
    query = " ".join(_string_list_arg(args, "query")).strip()
    if not query:
        raise IsxError("search query is required")
    return run_islands(cfg, ["search", query])


def cmd_remove(args: argparse.Namespace) -> int:
    """Remove an index by name or repo identity."""
    cfg = load_config()
    item = find_local_index(cfg, string_arg(args, "target"))
    if not item:
        raise IsxError(f"could not resolve local index: {string_arg(args, 'target')}")
    index_name = item.get("name")
    if not index_name:
        raise IsxError("matched index metadata is missing its name")
    print(f"Removing index: {index_name}", flush=True)
    remove_args = ["remove"]
    if _bool_arg(args, "force"):
        remove_args.append("--force")
    remove_args.append(str(index_name))
    return run_islands(cfg, remove_args)


def cmd_sync(args: argparse.Namespace) -> int:
    """Sync one or more indexes with upstream."""
    cfg = load_config()
    return run_islands(cfg, ["sync", *_string_list_arg(args, "targets")])


def cmd_reindex(args: argparse.Namespace) -> int:
    """Remove and rebuild an index from its clone URL."""
    cfg = load_config()
    index_name, repo_url = resolve_reindex_target(
        cfg, string_arg(args, "target"), cwd=Path.cwd()
    )
    if index_name:
        print(f"Removing existing index: {index_name}", flush=True)
        code = run_islands(cfg, ["remove", "--force", index_name])
        if code != 0:
            return code
    else:
        print(
            f"No existing local index matched {string_arg(args, 'target')}, adding fresh from URL",
            flush=True,
        )
    print(f"Adding repository: {repo_url}", flush=True)
    return _run_add_repository(args, repo_url, cfg=cfg)


def cmd_completions(args: argparse.Namespace) -> int:
    """Print shell completion script."""
    return print_completion(string_arg(args, "shell"))


def build_search_parser(
    subparsers: SubparserRegistry | None = None,
) -> argparse.ArgumentParser:
    """Build the ``search`` subcommand parser."""
    from slopgate.search._cli_parser import build_search_parser

    return build_search_parser(subparsers)
