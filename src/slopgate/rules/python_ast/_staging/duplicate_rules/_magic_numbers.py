"""Repeated magic-number hook rule."""

from __future__ import annotations

import ast
from collections import defaultdict
from typing import TYPE_CHECKING, final
from typing_extensions import override

from vibeforcer.constants import METADATA_PATH, PERMISSION_REQUEST, POST_TOOL_USE, PRE_TOOL_USE
from vibeforcer.lint._detectors.duplicates import _is_docstring_node
from vibeforcer.lint._helpers import build_parent_map as _build_parent_map
from vibeforcer.models import RuleFinding, Severity
from vibeforcer.rules.base import Rule, is_rule_enabled
from vibeforcer.rules.python_ast._staging.duplicate_rules._shared import _finding_count

from ..._helpers import decision_for_context, evaluate_common, parse_module

if TYPE_CHECKING:
    from vibeforcer.context import HookContext

def _is_reportable_number(
    node: ast.Constant, parent_map: dict[int, ast.AST], allowed_numbers: frozenset[int | float]
) -> bool:
    if isinstance(node.value, bool) or _is_docstring_node(node, parent_map):
        return False
    return isinstance(node.value, (int, float)) and node.value not in allowed_numbers


def _count_magic_numbers(
    module: ast.Module, allowed_numbers: frozenset[int | float]
) -> dict[int | float, int]:
    parent_map = _build_parent_map(module)
    counts: dict[int | float, int] = defaultdict(int)
    for node in ast.walk(module):
        if not isinstance(node, ast.Constant):
            continue
        value = node.value
        if isinstance(value, (int, float)) and _is_reportable_number(node, parent_map, allowed_numbers):
            counts[value] += 1
    return counts


@final
class PythonRepeatedMagicNumberRule(Rule):
    """Detect non-trivial numeric constants used more than N times in a file.

    Only scans the file being written.  Excludes common sentinel values
    (0, 1, -1) and docstrings.
    """

    rule_id = "PY-DUP-004"
    title = "Block repeated magic numbers"
    events = (PRE_TOOL_USE, PERMISSION_REQUEST, POST_TOOL_USE)

    _ALLOWED_NUMBERS = frozenset({0, 1, -1, 0.0, 1.0, -1.0, 2, 2.0})
    _MAX_OCCURRENCES = 3  # flag if a number appears more than this many times

    def _check_source(
        self, source: str, path_value: str, ctx: HookContext
    ) -> list[RuleFinding]:
        module = parse_module(source, ctx.config.python_ast_max_parse_chars)
        if module is None:
            return []

        counts = _count_magic_numbers(module, self._ALLOWED_NUMBERS)

        findings: list[RuleFinding] = []
        for val, count in counts.items():
            if count > self._MAX_OCCURRENCES:
                findings.append(RuleFinding(
                    rule_id=self.rule_id,
                    title=self.title,
                    severity=Severity.LOW,
                    decision=decision_for_context(ctx),
                    message=(
                        f"Magic number {repr(val)} appears {count} times in "
                        f"`{path_value}`. Extract into a named constant."
                    ),
                    metadata={
                        METADATA_PATH: path_value,
                        "value": val,
                        "count": count,
                    },
                ))
        # Only report the worst offender to avoid noise
        if findings:
            return [max(findings, key=_finding_count)]
        return findings

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        return evaluate_common(self, ctx, self._check_source)
