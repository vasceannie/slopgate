"""Parse Python sources for AST runtime rules."""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from slopgate.rules.base import is_rule_enabled
from slopgate.util.payloads import is_edit_like_tool

from .._helpers import parse_module

if TYPE_CHECKING:
    from slopgate.context import HookContext


@dataclass(frozen=True, slots=True)
class ParseFailure:
    """Structured Python parse-health failure.

    Carries non-source parser provenance so findings can explain why AST
    analysis could not run without storing any source text.
    """

    kind: str
    exception_type: str | None = None
    message: str | None = None
    line: int | None = None
    offset: int | None = None


def parse_strict(source: str, max_chars: int) -> ast.Module | None:
    """Parse source into a module; return None when too large or syntactically invalid."""
    if len(source) > max_chars:
        return None
    try:
        return ast.parse(source)
    except SyntaxError:
        return None


def first_significant_line(source: str) -> str:
    """Return the first non-empty, non-comment line from source."""
    for line in source.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return line
    return ""


def looks_like_indented_fragment(source: str, exc: SyntaxError) -> bool:
    """Return True when a parse error is probably an edit fragment, not a module."""
    if exc.msg != "unexpected indent":
        return False
    first_line = first_significant_line(source)
    return bool(first_line and first_line[:1].isspace())


def parse_health_failure(
    source: str,
    max_chars: int,
    *,
    suppress_fragments: bool,
) -> ParseFailure | None:
    """Return the structured health failure, or None when parseable/fragmental."""
    if len(source) > max_chars:
        return ParseFailure(kind="oversized")
    try:
        ast.parse(source)
    except RecursionError:
        return ParseFailure(kind="parse_error", exception_type="RecursionError")
    except SyntaxError as exc:
        if suppress_fragments and looks_like_indented_fragment(source, exc):
            return None
        return ParseFailure(
            kind="parse_error",
            exception_type=type(exc).__name__,
            message=exc.msg,
            line=exc.lineno,
            offset=exc.offset,
        )
    return None


def is_full_module_candidate(ctx: HookContext, source_kind: str) -> bool:
    """Return True when pre-edit content likely represents a full Python module.

    `Edit`, `MultiEdit`, and patch-style payloads frequently contain fragments rather
    than a complete file. Those fragments are still useful for targeted AST rules, but
    they should not trip the fail-closed AST health rule.
    """
    projection = ctx.tool_input.get("_slopgate_projection")
    if (
        isinstance(projection, dict)
        and projection.get("status") == "projected"
        and ctx.platform_event_name == "tool.execute.before"
        and source_kind == "multi_edit"
    ):
        return True
    tool_name = ctx.tool_name.lower()
    if source_kind in {"multi_edit", "multi_edit_old", "patch"}:
        return False
    if tool_name != "write" and is_edit_like_tool(ctx.tool_name):
        return False
    if tool_name in {
        "edit",
        "multiedit",
        "multi_edit",
        "patch",
        "applypatch",
        "apply_patch",
    }:
        return False
    return True


def resolve_python_path(ctx: HookContext, path_value: str) -> Path:
    """Resolve Python file paths consistently for AST-based rules."""
    raw_path = Path(path_value)
    if raw_path.is_absolute():
        return raw_path
    return (ctx.cwd / raw_path).resolve()


def line_count(source: str) -> int:
    """Return the line count in the same spirit as lint read_lines()."""
    return len(source.splitlines())


def parsed_nodes(source: str, ctx: HookContext) -> list[ast.AST]:
    module = parse_module(source, ctx.config.python_ast_max_parse_chars)
    return [] if module is None else list(ast.walk(module))


def parsed_functions(
    source: str,
    ctx: HookContext,
) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [
        node
        for node in parsed_nodes(source, ctx)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]


def parsed_classes(source: str, ctx: HookContext) -> list[ast.ClassDef]:
    return [
        node for node in parsed_nodes(source, ctx) if isinstance(node, ast.ClassDef)
    ]


def python_ast_rule_is_disabled(ctx: HookContext, rule_id: str) -> bool:
    return not is_rule_enabled(ctx, rule_id) or not ctx.config.python_ast_enabled
