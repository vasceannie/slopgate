"""Detect Python functions that exceed the configured line budget."""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from typing_extensions import override

from slopgate.constants import (
    BLOCK,
    DENY,
    METADATA_FUNCTION,
    METADATA_PATH,
    PERMISSION_REQUEST,
    POST_TOOL_USE,
    PRE_TOOL_USE,
)
from slopgate.models import RuleFinding, Severity
from slopgate.rules.base import Rule, is_rule_enabled
from ..._helpers import evaluate_common
from ..source_parse import parse_strict

if TYPE_CHECKING:
    from slopgate.context import HookContext


class PythonLongMethodRule(Rule):
    """Block long Python methods."""

    rule_id = "PY-CODE-008"
    title = "Block long Python methods"
    events = (PRE_TOOL_USE, PERMISSION_REQUEST, POST_TOOL_USE)

    @staticmethod
    def _worst_function(module: ast.Module, limit: int) -> tuple[str, int] | None:
        """Return (name, span) of the longest over-limit function, or None."""
        worst: tuple[str, int] | None = None
        for node in ast.walk(module):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.end_lineno is None:
                continue
            span = node.end_lineno - node.lineno + 1
            if span > limit and (worst is None or span > worst[1]):
                worst = (node.name, span)
        return worst

    def _check_source(
        self, source: str, path_value: str, ctx: HookContext
    ) -> list[RuleFinding]:
        """Return findings for any too-long functions in source."""
        module = parse_strict(source, ctx.config.python_ast_max_parse_chars)
        if module is None:
            return []
        worst = self._worst_function(module, ctx.config.python_long_method_lines)
        if worst is None:
            return []
        name, span = worst
        limit = ctx.config.python_long_method_lines
        decision = (
            DENY if ctx.event_name in (PRE_TOOL_USE, PERMISSION_REQUEST) else BLOCK
        )
        return [
            RuleFinding(
                rule_id=self.rule_id,
                title=self.title,
                severity=Severity.HIGH,
                decision=decision,
                message=(
                    f"Python function `{name}` in `{path_value}` is {span} "
                    f"lines long. Keep functions under {limit} lines or split "
                    "them into helpers."
                ),
                metadata={
                    METADATA_PATH: path_value,
                    METADATA_FUNCTION: name,
                    "lines": span,
                },
            )
        ]

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        return evaluate_common(self, ctx, self._check_source)
