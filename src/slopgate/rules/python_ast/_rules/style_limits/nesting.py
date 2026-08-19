"""Detect Python functions whose control-flow nesting is too deep."""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING, final

from typing_extensions import override

from slopgate.constants import (
    METADATA_FUNCTION,
    METADATA_PATH,
    PERMISSION_REQUEST,
    POST_TOOL_USE,
    PRE_TOOL_USE,
)
from slopgate.models import RuleFinding, Severity
from slopgate.rules.base import Rule, is_rule_enabled
from ..._helpers import decision_for_context, evaluate_common

if TYPE_CHECKING:
    from slopgate.context import HookContext
from ..source_parse import parsed_functions


@final
class PythonDeepNestingRule(Rule):
    """PY-CODE-011: Block functions with nesting depth > 4."""

    rule_id = "PY-CODE-011"
    title = "Block deep nesting"
    events = (PRE_TOOL_USE, PERMISSION_REQUEST, POST_TOOL_USE)
    _NESTING_TYPES = (
        ast.If,
        ast.For,
        ast.While,
        ast.AsyncFor,
        ast.With,
        ast.AsyncWith,
        ast.Try,
        ast.ExceptHandler,
    )

    def _max_nesting(self, node: ast.AST, depth: int = 0) -> int:
        """Return the maximum nesting depth below node."""
        max_d = depth
        for child in ast.iter_child_nodes(node):
            if isinstance(child, self._NESTING_TYPES):
                max_d = max(max_d, self._max_nesting(child, depth + 1))
            else:
                max_d = max(max_d, self._max_nesting(child, depth))
        return max_d

    def _check_source(
        self, source: str, path_value: str, ctx: HookContext
    ) -> list[RuleFinding]:
        worst_name = ""
        worst_depth = 0
        for node in parsed_functions(source, ctx):
            depth = self._max_nesting(node, 0)
            if depth > ctx.config.python_max_nesting_depth and depth > worst_depth:
                worst_name = node.name
                worst_depth = depth
        if not worst_name:
            return []
        limit = ctx.config.python_max_nesting_depth
        return [
            RuleFinding(
                rule_id=self.rule_id,
                title=self.title,
                severity=Severity.HIGH,
                decision=decision_for_context(ctx),
                message=(
                    f"Function `{worst_name}` in `{path_value}` has nesting "
                    f"depth {worst_depth}. Keep nesting at or below {limit} "
                    "levels."
                ),
                metadata={
                    METADATA_PATH: path_value,
                    METADATA_FUNCTION: worst_name,
                    "depth": worst_depth,
                },
            )
        ]

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        return evaluate_common(self, ctx, self._check_source)
