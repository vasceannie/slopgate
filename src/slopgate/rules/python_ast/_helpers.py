from __future__ import annotations

import ast
from collections import Counter
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from slopgate.models import RuleFinding
from slopgate.rules.base import Rule, is_rule_enabled
from slopgate.util.path_filters import is_authored_python_path
from slopgate.util.payloads import is_mutating_tool_use

if TYPE_CHECKING:
    from slopgate.context import HookContext

    CheckFn = Callable[[str, str, "HookContext"], list[RuleFinding]]


# Prefixes that signal a function family (parse_*, build_*, validate_*, …)
_FAMILY_PREFIXES = (
    "parse_",
    "build_",
    "create_",
    "make_",
    "get_",
    "set_",
    "validate_",
    "check_",
    "format_",
    "render_",
    "load_",
    "save_",
    "encode_",
    "decode_",
    "serialize_",
    "deserialize_",
)


def decision_for_context(ctx: HookContext) -> str:
    return "deny" if ctx.event_name in ("PreToolUse", "PermissionRequest") else "block"


def parse_module(source: str, max_chars: int) -> ast.Module | None:
    """Parse source into an AST module, respecting size limit."""
    if len(source) > max_chars:
        return None
    try:
        return ast.parse(source)
    except (SyntaxError, RecursionError):
        return None


def _read_candidate_source(ctx: HookContext, path_value: str) -> str | None:
    full_path = (
        (ctx.cwd / path_value).resolve()
        if not Path(path_value).is_absolute()
        else Path(path_value)
    )
    try:
        return full_path.read_text(encoding="utf-8")
    except OSError:
        return None


def _pre_tool_sources(ctx: HookContext) -> list[tuple[str, str]]:
    return [
        (ct.content, ct.path)
        for ct in ctx.content_targets
        if is_authored_python_path(ct.path)
    ]


def _post_tool_sources(ctx: HookContext) -> list[tuple[str, str]]:
    if not is_mutating_tool_use(ctx):
        return []
    sources: list[tuple[str, str]] = []
    for path_value in ctx.candidate_paths:
        if not is_authored_python_path(path_value):
            continue
        source = _read_candidate_source(ctx, path_value)
        if source is not None:
            sources.append((source, path_value))
    return sources


def _python_sources_for_context(ctx: HookContext) -> list[tuple[str, str]]:
    if ctx.event_name in ("PreToolUse", "PermissionRequest"):
        return _pre_tool_sources(ctx)
    return _post_tool_sources(ctx)


def evaluate_common(
    rule: Rule,
    ctx: HookContext,
    check_fn: CheckFn,
) -> list[RuleFinding]:
    """Shared evaluate logic for all Python AST rules."""
    if not is_rule_enabled(ctx, rule.rule_id):
        return []
    if not ctx.config.python_ast_enabled:
        return []
    findings: list[RuleFinding] = []
    for source, path_value in _python_sources_for_context(ctx):
        findings.extend(check_fn(source, path_value, ctx))
    return findings


def detect_family_prefix(names: list[str]) -> str | None:
    """Return the shared prefix if 3+ names share one, else None."""
    prefix_counts: Counter[str] = Counter()
    for name in names:
        for prefix in _FAMILY_PREFIXES:
            if name.startswith(prefix):
                prefix_counts[prefix] += 1
                break
    for prefix, count in prefix_counts.most_common(1):
        if count >= 3:
            return prefix
    return None
