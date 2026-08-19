"""Detect Python functions with too many parameters."""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING, final

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


@final
class PythonLongParameterRule(Rule):
    """Block long Python parameter lists."""

    rule_id = "PY-CODE-009"
    title = "Block long Python parameter lists"
    events = (PRE_TOOL_USE, PERMISSION_REQUEST, POST_TOOL_USE)

    @staticmethod
    def _worst_param_count(module: ast.Module, limit: int) -> tuple[str, int] | None:
        """Return (name, count) of the function with the most over-limit params."""
        worst: tuple[str, int] | None = None
        for node in ast.walk(module):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            args = (
                list(node.args.posonlyargs)
                + list(node.args.args)
                + list(node.args.kwonlyargs)
            )
            names = [arg.arg for arg in args]
            if names and names[0] in {"self", "cls"}:
                names = names[1:]
            if len(names) > limit and (worst is None or len(names) > worst[1]):
                worst = (node.name, len(names))
        return worst

    def _check_source(
        self, source: str, path_value: str, ctx: HookContext
    ) -> list[RuleFinding]:
        """Return findings for any too-long parameter lists in source."""
        module = parse_strict(source, ctx.config.python_ast_max_parse_chars)
        if module is None:
            return []
        worst = self._worst_param_count(module, ctx.config.python_long_parameter_limit)
        if worst is None:
            return []
        name, count = worst
        limit = ctx.config.python_long_parameter_limit
        decision = (
            DENY if ctx.event_name in (PRE_TOOL_USE, PERMISSION_REQUEST) else BLOCK
        )
        return [
            RuleFinding(
                rule_id=self.rule_id,
                title=self.title,
                severity=Severity.MEDIUM,
                decision=decision,
                message=(
                    f"Python function `{name}` in `{path_value}` declares "
                    f"{count} parameters. Keep functions at or below {limit} "
                    "parameters or group inputs into objects."
                ),
                metadata={
                    METADATA_PATH: path_value,
                    METADATA_FUNCTION: name,
                    "parameter_count": count,
                },
            )
        ]

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        return evaluate_common(self, ctx, self._check_source)
