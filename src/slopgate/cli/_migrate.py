"""One-shot filesystem migration from quality_gate naming."""

from __future__ import annotations
import argparse
import re
import shutil
import sys
from pathlib import Path
from slopgate.config._discovery import config_dir
from slopgate.util.platform import is_windows, user_config_dir

_LEGACY_CONFIG_NAMES: tuple[str, ...] = ()
_LEGACY_REPO_MARKER = "quality_gate.toml"
_REPO_MARKER = "slopgate.toml"
_LEGACY_SENTINELS = (".noqualitygate", ".no-quality-gate")
_SENTINELS = (".noslopgate", ".no-slop-gate")
_LEGACY_OPENCODE_PLUGIN: str | None = None
_OPENCODE_PLUGIN = "slopgate-plugin.ts"


def _bool_arg(args: argparse.Namespace, name: str) -> bool:
    value = getattr(args, name, False)
    return value if isinstance(value, bool) else False


def string_arg(args: argparse.Namespace, name: str, default: str = ".") -> str:
    value = getattr(args, name, default)
    return value if isinstance(value, str) else default


def _rewrite_toml_sections(text: str) -> str:
    return re.sub("^\\[quality_gate\\]", "[slopgate]", text, flags=re.MULTILINE)


def _migrate_repo_marker(root: Path, *, dry_run: bool) -> list[str]:
    actions: list[str] = []
    legacy = root / _LEGACY_REPO_MARKER
    target = root / _REPO_MARKER
    if legacy.exists() and (not target.exists()):
        content = _rewrite_toml_sections(legacy.read_text(encoding="utf-8"))
        actions.append(f"write {target}")
        if not dry_run:
            _ = target.write_text(content, encoding="utf-8")
            legacy.unlink()
    elif legacy.exists() and target.exists():
        actions.append(f"remove duplicate legacy {legacy}")
        if not dry_run:
            legacy.unlink()
    for old_name, new_name in zip(_LEGACY_SENTINELS, _SENTINELS, strict=True):
        old_path = root / old_name
        new_path = root / new_name
        if not old_path.exists():
            continue
        if new_path.exists():
            actions.append(f"remove legacy sentinel {old_path}")
            if not dry_run:
                old_path.unlink()
            continue
        actions.append(f"rename {old_path} -> {new_path}")
        if not dry_run:
            old_path.rename(new_path)
    return actions


def _legacy_config_dir() -> Path:
    if is_windows():
        return user_config_dir("slopgate")
    xdg = Path.home() / ".config" / "slopgate"
    return xdg


def _migrate_user_config(*, dry_run: bool, force: bool) -> list[str]:
    actions: list[str] = []
    target = config_dir()
    for legacy_name in _LEGACY_CONFIG_NAMES:
        legacy = (
            _legacy_config_dir()
            if legacy_name == "slopgate"
            else Path.home() / ".config" / legacy_name
        )
        if not legacy.exists():
            continue
        if target.exists() and (not force):
            print(
                f"error: {target} already exists; use --force to replace after backup",
                file=sys.stderr,
            )
            raise SystemExit(1)
        actions.append(f"move {legacy} -> {target}")
        if not dry_run:
            if target.exists():
                backup = target.with_name(f"{target.name}.slopgate-migrate-bak")
                if backup.exists():
                    shutil.rmtree(backup)
                shutil.move(str(target), str(backup))
            shutil.move(str(legacy), str(target))
    return actions


def _migrate_opencode_plugin(*, dry_run: bool) -> list[str]:
    actions: list[str] = []
    from slopgate.installer._suite import OPENCODE_PLATFORM
    from slopgate.util.platform import user_config_dir

    plugins_dir = user_config_dir(OPENCODE_PLATFORM) / "plugins"
    if _LEGACY_OPENCODE_PLUGIN is None:
        return actions
    legacy = plugins_dir / _LEGACY_OPENCODE_PLUGIN
    target = plugins_dir / _OPENCODE_PLUGIN
    if legacy.exists() and (not target.exists()):
        actions.append(f"rename {legacy} -> {target}")
        if not dry_run:
            legacy.rename(target)
    elif legacy.exists():
        actions.append(f"remove legacy plugin {legacy}")
        if not dry_run:
            legacy.unlink()
    return actions


def cmd_migrate(args: argparse.Namespace) -> int:
    dry_run = _bool_arg(args, "dry_run")
    force = _bool_arg(args, "force")
    repo_root = Path(string_arg(args, "path")).resolve()
    user_only = _bool_arg(args, "user_only")
    repo_only = _bool_arg(args, "repo_only")
    actions: list[str] = []
    if not repo_only:
        actions.extend(_migrate_user_config(dry_run=dry_run, force=force))
        actions.extend(_migrate_opencode_plugin(dry_run=dry_run))
    if not user_only:
        actions.extend(_migrate_repo_marker(repo_root, dry_run=dry_run))
    if not actions:
        print("Nothing to migrate.")
        return 0
    prefix = "[dry-run] " if dry_run else ""
    for action in actions:
        print(f"{prefix}{action}")
    return 0
