from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path


def _bool_arg(args: argparse.Namespace, name: str, default: bool = False) -> bool:
    value = getattr(args, name, default)
    return value if isinstance(value, bool) else default


def _copy_prompt_context(base_dir: Path, resource_path: Callable[[str], Path]) -> None:
    ctx_dir = base_dir / "prompt_context"
    if ctx_dir.exists():
        return
    ctx_dir.mkdir(parents=True, exist_ok=True)
    for name in ("organization.md", "repo.md"):
        src = resource_path("prompt_context") / name
        if src.exists():
            _ = (ctx_dir / name).write_text(
                src.read_text(encoding="utf-8"), encoding="utf-8"
            )
    print(f"Created: {ctx_dir}")


def cmd_config_show(_args: argparse.Namespace) -> int:
    from vibeforcer.config import load_config, resolve_config_path

    config_path = resolve_config_path()
    config = load_config()
    print(f"# Config source: {config_path}")
    print(f"# Trace dir: {config.trace_dir}")
    print(f"# Root: {config.root}")
    rules_msg = (
        f"{len(config.enabled_rules)} toggles, {len(config.regex_rules)} regex rules"
    )
    print(f"# Rules: {rules_msg}")
    print(f"# Python AST: {'enabled' if config.python_ast_enabled else 'disabled'}")
    print()
    print(
        json.dumps(
            {
                "config_path": str(config_path),
                "root": str(config.root),
                "trace_dir": str(config.trace_dir),
                "enabled_rules_count": len(config.enabled_rules),
                "regex_rules_count": len(config.regex_rules),
                "python_ast_enabled": config.python_ast_enabled,
                "protected_paths": config.protected_paths,
                "skip_paths": config.skip_paths,
            },
            indent=2,
        )
    )
    return 0


def cmd_config_init(args: argparse.Namespace) -> int:
    from vibeforcer.config import config_dir
    from vibeforcer.installer._shared import backup_existing_file_and_report
    from vibeforcer.resources import resource_path

    target = config_dir() / "config.json"
    if target.exists() and not _bool_arg(args, "force"):
        print(f"Config already exists: {target}")
        print("Use --force to overwrite.")
        return 1

    defaults_path = resource_path("defaults.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    backup_existing_file_and_report(target, "config")
    _ = target.write_text(defaults_path.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Created: {target}")

    log_dir = config_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "async").mkdir(exist_ok=True)
    print(f"Created: {log_dir}")
    _copy_prompt_context(config_dir(), resource_path)
    return 0


def cmd_config_path(_args: argparse.Namespace) -> int:
    from vibeforcer.config import resolve_config_path

    print(resolve_config_path())
    return 0
