"""Semantic clone hook rule."""

from __future__ import annotations

import ast
from collections import defaultdict
from typing import TYPE_CHECKING, final
from typing_extensions import override

from vibeforcer.constants import METADATA_PATH, PERMISSION_REQUEST, POST_TOOL_USE, PRE_TOOL_USE
from vibeforcer.lint._detectors.duplicates import (
    _has_skip_decorator,
    _normalize_ast,
    _skip_docstring,
    _structure_hash,
)
from vibeforcer.models import RuleFinding, Severity
from vibeforcer.rules.base import Rule, is_rule_enabled

from ..._helpers import decision_for_context, evaluate_common, parse_module

if TYPE_CHECKING:
    from vibeforcer.context import HookContext

def _semantic_clone_groups(
    module: ast.Module,
    *,
    min_body_lines: int,
) -> dict[str, list[tuple[str, int]]]:
    groups: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for node in ast.walk(module):
        candidate = _semantic_clone_candidate(node, min_body_lines=min_body_lines)
        if candidate is None:
            continue
        body = _skip_docstring(candidate.body)
        canonical = "|".join(_normalize_ast(stmt) for stmt in body)
        groups[_structure_hash(canonical)].append((candidate.name, candidate.lineno))
    return groups


def _semantic_clone_candidate(
    node: ast.AST,
    *,
    min_body_lines: int,
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return None
    if node.name.startswith("__") and node.name.endswith("__"):
        return None
    if _has_skip_decorator(node):
        return None
    if not _skip_docstring(node.body):
        return None
    if node.end_lineno and (node.end_lineno - node.lineno) < min_body_lines:
        return None
    return node


def _semantic_clone_finding(
    *,
    ctx: HookContext,
    path_value: str,
    clone_hash: str,
    members: list[tuple[str, int]],
) -> RuleFinding:
    others = [f"{name} (line {line_number})" for name, line_number in members[1:]]
    return RuleFinding(
        rule_id=PythonSemanticCloneRule.rule_id,
        title=PythonSemanticCloneRule.title,
        severity=Severity.MEDIUM,
        decision=decision_for_context(ctx),
        message=(
            f"Semantic clone in `{path_value}`: `{members[0][0]}` "
            f"has identical structure to {', '.join(others[:3])}. "
            "Parameterise or extract a shared implementation."
        ),
        metadata={
            METADATA_PATH: path_value,
            "function": members[0][0],
            "hash": clone_hash,
            "clones": [name for name, _ in members],
        },
    )


def _semantic_clone_findings(
    groups: dict[str, list[tuple[str, int]]],
    *,
    ctx: HookContext,
    path_value: str,
) -> list[RuleFinding]:
    return [
        _semantic_clone_finding(
            ctx=ctx,
            path_value=path_value,
            clone_hash=clone_hash,
            members=members,
        )
        for clone_hash, members in groups.items()
        if len(members) >= 2
    ]


@final
class PythonSemanticCloneRule(Rule):
    """Detect functions in the same file with identical AST structure
    despite different names.  Catches parameterised copy-paste.
    """

    rule_id = "PY-DUP-003"
    title = "Block semantic clones"
    events = (PRE_TOOL_USE, PERMISSION_REQUEST, POST_TOOL_USE)

    _MIN_BODY_LINES = 3  # skip trivial one-liners

    def _check_source(
        self, source: str, path_value: str, ctx: HookContext
    ) -> list[RuleFinding]:
        module = parse_module(source, ctx.config.python_ast_max_parse_chars)
        if module is None:
            return []

        groups = _semantic_clone_groups(module, min_body_lines=self._MIN_BODY_LINES)
        return _semantic_clone_findings(groups, ctx=ctx, path_value=path_value)

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        return evaluate_common(self, ctx, self._check_source)
