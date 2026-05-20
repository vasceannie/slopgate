"""Repeated block hook rule."""

from __future__ import annotations

import ast
from collections import defaultdict
from typing import TYPE_CHECKING, final
from typing_extensions import override

from vibeforcer.constants import METADATA_PATH, PERMISSION_REQUEST, POST_TOOL_USE, PRE_TOOL_USE
from vibeforcer.lint._detectors.duplicates import (
    _is_import_stmt,
    _normalize_ast,
    _skip_docstring,
    _structure_hash,
)
from vibeforcer.models import RuleFinding, Severity
from vibeforcer.rules.base import Rule, is_rule_enabled
from vibeforcer.rules.python_ast._staging.duplicate_rules._shared import _MIN_BLOCK_SIZE

from ..._helpers import decision_for_context, evaluate_common, parse_module

if TYPE_CHECKING:
    from vibeforcer.context import HookContext

def _strip_module_preamble(body: list[ast.stmt]) -> list[ast.stmt]:
    """Remove the contiguous top-of-file docstring/import preamble."""
    stripped = _skip_docstring(body)
    idx = 0
    while idx < len(stripped) and _is_import_stmt(stripped[idx]):
        idx += 1
    return stripped[idx:]


def _block_scopes(module: ast.Module) -> list[tuple[str, list[ast.stmt]]]:
    scopes: list[tuple[str, list[ast.stmt]]] = []
    for node in ast.walk(module):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            scopes.append((node.name, _skip_docstring(node.body)))
        elif isinstance(node, ast.Module):
            scopes.append(("<module>", _strip_module_preamble(node.body)))
    return scopes


def _record_block_windows(
    groups: dict[str, list[tuple[str, int, int]]], scope: str, body: list[ast.stmt]
) -> None:
    if len(body) < _MIN_BLOCK_SIZE:
        return
    norms = [_normalize_ast(stmt) for stmt in body]
    for start_index in range(len(norms) - _MIN_BLOCK_SIZE + 1):
        if all(_is_import_stmt(body[index]) for index in range(start_index, start_index + _MIN_BLOCK_SIZE)):
            continue
        h = _structure_hash("|".join(norms[start_index : start_index + _MIN_BLOCK_SIZE]))
        end_node = body[start_index + _MIN_BLOCK_SIZE - 1]
        end_lineno = end_node.end_lineno or body[start_index].lineno
        groups[h].append((scope, body[start_index].lineno, end_lineno))


def _repeated_block_finding(
    *,
    ctx: HookContext,
    path_value: str,
    block_hash: str,
    members: list[tuple[str, int, int]],
) -> RuleFinding:
    worst = max(members, key=lambda member: member[2] - member[1])
    scope, start, end = worst
    other_locs = [
        f"{other_scope}:{other_start}-{other_end}"
        for other_scope, other_start, other_end in members
        if (other_scope, other_start, other_end) != worst
    ]
    return RuleFinding(
        rule_id=PythonRepeatedBlocksRule.rule_id,
        title=PythonRepeatedBlocksRule.title,
        severity=Severity.MEDIUM,
        decision=decision_for_context(ctx),
        message=(
            f"Repeated code block in `{path_value}` at lines {start}-{end} "
            f"in `{scope}`. Identical block also appears at: "
            f"{', '.join(other_locs[:3])}. Extract into a shared helper."
        ),
        metadata={
            METADATA_PATH: path_value,
            "scope": scope,
            "start": start,
            "end": end,
            "hash": block_hash,
            "occurrences": len(members),
        },
    )


def _repeated_block_findings(
    groups: dict[str, list[tuple[str, int, int]]],
    *,
    ctx: HookContext,
    path_value: str,
) -> list[RuleFinding]:
    return [
        _repeated_block_finding(
            ctx=ctx,
            path_value=path_value,
            block_hash=block_hash,
            members=members,
        )
        for block_hash, members in groups.items()
        if len(members) >= 2
    ]


@final
class PythonRepeatedBlocksRule(Rule):
    """Detect blocks of 3+ consecutive statements that appear multiple times
    in the same file.  Catches copy-paste sprawl at write time.

    This is a single-file check: it only scans the file being written,
    not the whole project.  Full cross-file detection remains a lint-only
    concern (too expensive for a reactive hook).
    """

    rule_id = "PY-DUP-001"
    title = "Block repeated code blocks"
    events = (PRE_TOOL_USE, PERMISSION_REQUEST, POST_TOOL_USE)

    def _check_source(
        self, source: str, path_value: str, ctx: HookContext
    ) -> list[RuleFinding]:
        module = parse_module(source, ctx.config.python_ast_max_parse_chars)
        if module is None:
            return []

        groups: dict[str, list[tuple[str, int, int]]] = defaultdict(list)
        for scope, body in _block_scopes(module):
            _record_block_windows(groups, scope, body)
        return _repeated_block_findings(groups, ctx=ctx, path_value=path_value)

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        return evaluate_common(self, ctx, self._check_source)
