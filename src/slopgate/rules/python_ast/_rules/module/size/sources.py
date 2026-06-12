"""Source projection helpers for oversized Python module guardrails."""

from __future__ import annotations

from typing import TYPE_CHECKING

from slopgate._types import ObjectDict, object_dict, object_list
from slopgate.constants import (
    LINT_MAX_MODULE_LINES_SOFT,
    PERMISSION_REQUEST,
    PRE_TOOL_USE,
)
from slopgate.util.path_filters import is_authored_python_path
from slopgate.util.payloads import (
    extract_path_from_mapping,
    first_present,
    is_mutating_tool_use,
)

from ..._source_parse import line_count, resolve_python_path

if TYPE_CHECKING:
    from slopgate.context import HookContext


def _significant_line_fingerprint(source: str) -> tuple[str, ...]:
    """Return content lines after removing blank-line padding only."""
    return tuple(line.rstrip() for line in source.splitlines() if line.strip())


def is_line_count_camouflage(before: str, after: str) -> bool:
    """Detect blank-line/spacing shaving on an already-oversized module."""
    before_lines = line_count(before)
    after_lines = line_count(after)
    return (
        before_lines > LINT_MAX_MODULE_LINES_SOFT
        and after_lines < before_lines
        and _significant_line_fingerprint(before)
        == _significant_line_fingerprint(after)
    )


def read_python_source(ctx: HookContext, path_value: str) -> str | None:
    """Read a Python path relative to the hook cwd; return None on failure."""
    try:
        return resolve_python_path(ctx, path_value).read_text(encoding="utf-8")
    except OSError:
        return None


def _project_source_replacement(
    ctx: HookContext,
    path_value: str,
    old_string: str,
    new_string: str,
) -> tuple[str, str] | None:
    if not old_string:
        return None
    source = read_python_source(ctx, path_value)
    if source is None or old_string not in source:
        return None
    return source, source.replace(old_string, new_string, 1)


def project_replacement(
    ctx: HookContext,
    path_value: str,
    old_string: str,
    new_string: str,
) -> str | None:
    """Return projected file content after a single replacement edit."""
    replacement = _project_source_replacement(ctx, path_value, old_string, new_string)
    return None if replacement is None else replacement[1]


def _replacement_strings(tool_input: ObjectDict) -> tuple[str, str]:
    old_string = first_present(
        tool_input,
        ("old_string", "oldString", "old_text", "oldText"),
        strip=False,
    )
    new_string = first_present(
        tool_input,
        ("new_string", "newString", "new_text", "newText"),
        strip=False,
    )
    return old_string, new_string


def _top_level_python_path(tool_input: ObjectDict) -> str | None:
    path_value = extract_path_from_mapping(tool_input)
    if not path_value or not is_authored_python_path(path_value):
        return None
    return path_value


def _project_top_level_source_replacement(
    ctx: HookContext,
    tool_input: ObjectDict,
) -> tuple[str, str, str] | None:
    path_value = _top_level_python_path(tool_input)
    if path_value is None:
        return None
    old_string, new_string = _replacement_strings(tool_input)
    replacement = _project_source_replacement(ctx, path_value, old_string, new_string)
    if replacement is None:
        return None
    source, projected = replacement
    return path_value, source, projected


def project_top_level_edit(
    ctx: HookContext, tool_input: ObjectDict
) -> tuple[str, str] | None:
    """Project a Claude/OpenCode-style single Edit payload into final source."""
    replacement = _project_top_level_source_replacement(ctx, tool_input)
    if replacement is None:
        return None
    path_value, _source, projected = replacement
    return path_value, projected


def project_multiedit_sources(
    ctx: HookContext, tool_input: ObjectDict
) -> list[tuple[str, str]]:
    """Project MultiEdit payloads into final per-file source content."""
    default_path = extract_path_from_mapping(tool_input)
    projected_by_path: dict[str, str] = {}
    for item in object_list(tool_input.get("edits")):
        item_dict = object_dict(item)
        path_value = extract_path_from_mapping(item_dict) or default_path
        if not path_value or not is_authored_python_path(path_value):
            continue
        source = projected_by_path.get(path_value)
        if source is None:
            source = read_python_source(ctx, path_value)
        if source is None:
            continue
        old_string = first_present(
            item_dict,
            ("old_string", "oldString", "old_text", "oldText"),
            strip=False,
        )
        new_string = first_present(
            item_dict,
            ("new_string", "newString", "new_text", "newText"),
            strip=False,
        )
        if old_string and old_string in source:
            projected_by_path[path_value] = source.replace(old_string, new_string, 1)
    return [(path_value, source) for path_value, source in projected_by_path.items()]


def dedupe_sources(sources: list[tuple[str, str]]) -> list[tuple[str, str]]:
    deduped: dict[tuple[str, str], None] = {}
    for source in sources:
        deduped.setdefault(source, None)
    return list(deduped)


def pre_python_structural_sources(ctx: HookContext) -> list[tuple[str, str]]:
    sources: list[tuple[str, str]] = []
    top_level_projection = project_top_level_edit(ctx, ctx.tool_input)
    if top_level_projection is not None:
        sources.append(top_level_projection)
    sources.extend(project_multiedit_sources(ctx, ctx.tool_input))
    for ct in ctx.content_targets:
        if is_authored_python_path(ct.path) and ct.source not in {
            "multi_edit",
            "multi_edit_old",
        }:
            sources.append((ct.path, ct.content))
    return sources


def post_python_structural_sources(ctx: HookContext) -> list[tuple[str, str]]:
    if not is_mutating_tool_use(ctx):
        return []
    sources: list[tuple[str, str]] = []
    for path_value in ctx.candidate_paths:
        if not is_authored_python_path(path_value):
            continue
        source = read_python_source(ctx, path_value)
        if source is not None:
            sources.append((path_value, source))
    return sources


def pre_python_camouflage_sources(ctx: HookContext) -> list[tuple[str, str, str]]:
    if ctx.event_name not in (PRE_TOOL_USE, PERMISSION_REQUEST):
        return []
    sources: list[tuple[str, str, str]] = []
    top_level_projection = _project_top_level_source_replacement(ctx, ctx.tool_input)
    if top_level_projection is not None:
        sources.append(top_level_projection)
    for path_value, projected in project_multiedit_sources(ctx, ctx.tool_input):
        before = read_python_source(ctx, path_value)
        if before is not None:
            sources.append((path_value, before, projected))
    for ct in ctx.content_targets:
        if not is_authored_python_path(ct.path) or ct.source in {
            "multi_edit",
            "multi_edit_old",
        }:
            continue
        before = read_python_source(ctx, ct.path)
        if before is not None:
            sources.append((ct.path, before, ct.content))
    return _dedupe_camouflage_sources(sources)


def _dedupe_camouflage_sources(
    sources: list[tuple[str, str, str]],
) -> list[tuple[str, str, str]]:
    deduped: dict[tuple[str, str], tuple[str, str, str]] = {}
    for path_value, before, after in sources:
        deduped.setdefault((path_value, after), (path_value, before, after))
    return list(deduped.values())


def python_structural_sources(ctx: HookContext) -> list[tuple[str, str]]:
    """Return full/projection Python sources for size-oriented hook checks.

    Unlike general AST rules, size checks must understand both complete-file
    writes and edit payloads whose final file crosses a threshold.
    """
    if ctx.event_name in (PRE_TOOL_USE, PERMISSION_REQUEST):
        return dedupe_sources(pre_python_structural_sources(ctx))
    return dedupe_sources(post_python_structural_sources(ctx))
