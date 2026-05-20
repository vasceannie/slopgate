"""Duplicate call-sequence hook rule."""

from __future__ import annotations

import ast
from collections import defaultdict
from typing import TYPE_CHECKING, final
from typing_extensions import override

from vibeforcer.constants import METADATA_PATH, PERMISSION_REQUEST, POST_TOOL_USE, PRE_TOOL_USE
from vibeforcer.lint._detectors.duplicates import _extract_call_sequence
from vibeforcer.models import RuleFinding, Severity
from vibeforcer.rules.base import Rule, is_rule_enabled

from ..._helpers import decision_for_context, evaluate_common, parse_module

if TYPE_CHECKING:
    from vibeforcer.context import HookContext

def _function_call_sequence_groups(
    module: ast.Module,
    *,
    min_calls: int,
) -> dict[tuple[str, ...], list[tuple[str, int]]]:
    groups: dict[tuple[str, ...], list[tuple[str, int]]] = defaultdict(list)
    for node in ast.walk(module):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        seq = _extract_call_sequence(node)
        if len(seq) >= min_calls:
            groups[seq].append((node.name, node.lineno))
    return groups


def _duplicate_call_sequence_finding(
    *,
    ctx: HookContext,
    path_value: str,
    seq: tuple[str, ...],
    members: list[tuple[str, int]],
) -> RuleFinding:
    seq_preview = ", ".join(seq[:5]) + ("..." if len(seq) > 5 else "")
    others = [f"{name} (line {line_number})" for name, line_number in members[1:]]
    return RuleFinding(
        rule_id=PythonDuplicateCallSequenceRule.rule_id,
        title=PythonDuplicateCallSequenceRule.title,
        severity=Severity.MEDIUM,
        decision=decision_for_context(ctx),
        message=(
            f"Duplicate call sequence in `{path_value}`: "
            f"`{members[0][0]}` and {len(members) - 1} other function(s) "
            f"make the same ordered calls [{seq_preview}]. "
            f"Duplicated in: {', '.join(others[:3])}. Extract shared logic."
        ),
        metadata={
            METADATA_PATH: path_value,
            "function": members[0][0],
            "sequence": list(seq),
            "duplicates": [name for name, _ in members],
        },
    )


def _duplicate_call_sequence_findings(
    groups: dict[tuple[str, ...], list[tuple[str, int]]],
    *,
    ctx: HookContext,
    path_value: str,
) -> list[RuleFinding]:
    return [
        _duplicate_call_sequence_finding(
            ctx=ctx,
            path_value=path_value,
            seq=seq,
            members=members,
        )
        for seq, members in groups.items()
        if len(members) >= 2
    ]


@final
class PythonDuplicateCallSequenceRule(Rule):
    """Detect functions in the same file that make the same ordered sequence
    of calls.  Single-file scope for hook performance.
    """

    rule_id = "PY-DUP-002"
    title = "Block duplicate call sequences"
    events = (PRE_TOOL_USE, PERMISSION_REQUEST, POST_TOOL_USE)

    _MIN_CALLS = 3  # minimum sequence length to flag

    def _check_source(
        self, source: str, path_value: str, ctx: HookContext
    ) -> list[RuleFinding]:
        module = parse_module(source, ctx.config.python_ast_max_parse_chars)
        if module is None:
            return []

        groups = _function_call_sequence_groups(module, min_calls=self._MIN_CALLS)
        return _duplicate_call_sequence_findings(groups, ctx=ctx, path_value=path_value)

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        return evaluate_common(self, ctx, self._check_source)
