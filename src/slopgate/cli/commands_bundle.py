"""CLI handlers for packaged Slopgate bundle assets."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import cast

from slopgate.installer._install_scope import INSTALL_SCOPE_USER


def _sync_status(changed: bool, dry_run: bool, remove: bool) -> tuple[str, str]:
    action = "remove" if remove else "update"
    if dry_run:
        return ("DRY-RUN", f"would {action}" if changed else "would keep")
    if not changed:
        return ("OK", "unchanged")
    return ("REMOVED", "removed") if remove else ("UPDATED", "updated")


def _namespace_string(args: argparse.Namespace, name: str, default: str = "") -> str:
    value = getattr(args, name, default)
    return value if isinstance(value, str) else default


def _namespace_bool(args: argparse.Namespace, name: str) -> bool:
    value = getattr(args, name, False)
    return value if isinstance(value, bool) else False


def _namespace_project_root(args: argparse.Namespace) -> Path | None:
    value = _namespace_string(args, "project_root")
    return Path(value).resolve() if value else None


def cmd_bundle_sync_prompts(args: argparse.Namespace) -> int:
    """Append or refresh package-managed Slopgate prompt-routing blocks."""

    from slopgate.bundle_prompt_sync import (
        PromptScope,
        PromptSyncOptions,
        sync_skill_routing_prompts,
    )

    try:
        install_scope = cast(
            PromptScope,
            _namespace_string(args, "install_scope", INSTALL_SCOPE_USER),
        )
        remove = _namespace_bool(args, "remove")
        results = sync_skill_routing_prompts(
            platforms=(_namespace_string(args, "only", "all"),),
            scope=install_scope,
            project_root=_namespace_project_root(args),
            options=PromptSyncOptions(
                dry_run=_namespace_bool(args, "dry_run"),
                remove=remove,
            ),
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    for result in results:
        prefix, verb = _sync_status(result.changed, result.dry_run, remove)
        print(f"{prefix} {result.platform}:{result.scope} {verb}: {result.path}")
    return 0
