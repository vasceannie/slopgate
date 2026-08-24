from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path

from slopgate._types import is_object_dict, object_list


_CLAUDE_SKILL_PROTECTED_PATHS = frozenset({".claude/", ".claude/skills/"})


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
    from slopgate.config import load_config, resolve_config_path

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
    from slopgate.config import config_dir
    from slopgate.installer._shared import backup_existing_file_and_report
    from slopgate.resources import resource_path

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


def _read_config_document(config_path: Path) -> dict[str, object] | None:
    try:
        raw_config = json.loads(config_path.read_text(encoding="utf-8"))
    except OSError as exc:
        print(f"Could not read config {config_path}: {exc}", file=sys.stderr)
        return None
    except json.JSONDecodeError as exc:
        print(f"Config is not valid JSON: {exc}", file=sys.stderr)
        return None
    if not is_object_dict(raw_config):
        print(f"Config must be a JSON object: {config_path}", file=sys.stderr)
        return None
    return raw_config


def _remove_claude_skill_protections(config: dict[str, object]) -> bool | None:
    protected_value = config.get("protected_paths")
    if protected_value is None:
        return False
    protected_paths: list[str] = []
    for value in object_list(protected_value):
        if not isinstance(value, str):
            print("protected_paths must contain only strings", file=sys.stderr)
            return None
        protected_paths.append(value)
    updated_paths = [
        path for path in protected_paths if path not in _CLAUDE_SKILL_PROTECTED_PATHS
    ]
    if updated_paths == protected_paths:
        return False
    config["protected_paths"] = updated_paths
    return True


def _write_config_document(config_path: Path, config: dict[str, object]) -> int:
    from slopgate.installer._shared import backup_existing_file_and_report

    backup_existing_file_and_report(config_path, "config")
    try:
        _ = config_path.write_text(
            json.dumps(config, indent=2) + "\n", encoding="utf-8"
        )
    except OSError as exc:
        print(f"Could not write config {config_path}: {exc}", file=sys.stderr)
        return 1
    return 0


def cmd_config_allow_skill_directories(_args: argparse.Namespace) -> int:
    """Allow Claude skill directories in the active configuration."""
    from slopgate.config import resolve_config_path

    config_path = resolve_config_path()
    if not config_path.exists():
        print(f"Config file not found: {config_path}", file=sys.stderr)
        return 1
    config = _read_config_document(config_path)
    if config is None:
        return 1
    changed = _remove_claude_skill_protections(config)
    if changed is None:
        return 1
    if not changed:
        print(f"Claude skill directories already allowed in {config_path}")
        return 0
    if _write_config_document(config_path, config) != 0:
        return 1
    print(f"Allowed Claude skill directories in {config_path}")
    return 0


def cmd_config_path(_args: argparse.Namespace) -> int:
    from slopgate.config import resolve_config_path

    print(resolve_config_path())
    return 0
