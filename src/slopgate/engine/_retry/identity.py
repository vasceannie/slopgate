"""Exact diagnostic fingerprints and semantic enforcement identities."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from slopgate.config import resolve_repo_root
from slopgate.constants import METADATA_TOOL_NAME
from slopgate.context import HookContext
from slopgate.models import RuleFinding
from slopgate.state import SemanticRetryKey
from slopgate.util.payloads import is_edit_like_tool

from .._hints import finding_path


def normalize_attempt_path(ctx: HookContext, path_value: str) -> str:
    raw_path = Path(path_value)
    if raw_path.is_absolute():
        return str(raw_path.resolve(strict=False))
    return str((ctx.cwd / raw_path).resolve(strict=False))


def operation_category(ctx: HookContext) -> str:
    if is_edit_like_tool(ctx.tool_name):
        return "edit"
    normalized = ctx.tool_name.strip().casefold()
    if normalized in {"bash", "shell", "powershell"}:
        return "shell"
    if normalized == "read":
        return "read"
    if normalized in {"grep", "glob", "search", "websearch"}:
        return "search"
    return normalized or "unknown"


def _stable_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def attempt_fingerprint(ctx: HookContext) -> str | None:
    if not is_edit_like_tool(ctx.tool_name):
        return None
    payload = {
        METADATA_TOOL_NAME: ctx.tool_name.lower(),
        "candidate_paths": sorted(
            {
                normalize_attempt_path(ctx, path_value)
                for path_value in ctx.candidate_paths
                if path_value
            }
        ),
        "targets": sorted(
            {
                (
                    normalize_attempt_path(ctx, target.path),
                    target.source,
                    hashlib.sha256(target.content.encode("utf-8")).hexdigest(),
                )
                for target in ctx.content_targets
                if target.path
            }
        ),
        "tool_input_hash": _stable_hash(ctx.tool_input),
    }
    if not payload["candidate_paths"] and not payload["targets"]:
        return None
    return _stable_hash(payload)


def semantic_enforcement_key(ctx: HookContext, item: RuleFinding) -> SemanticRetryKey:
    path_value = finding_path(item)
    normalized_path = normalize_attempt_path(ctx, path_value) if path_value else None
    repo_root = (resolve_repo_root(ctx.cwd) or ctx.cwd).resolve(strict=False)
    return SemanticRetryKey(
        session_id=ctx.session_id.strip(),
        repo_root=str(repo_root),
        rule_id=item.rule_id.strip(),
        path=normalized_path,
        operation_category=None if normalized_path else operation_category(ctx),
    )
