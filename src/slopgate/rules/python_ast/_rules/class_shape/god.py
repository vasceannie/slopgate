"""Detect classes that exceed method-count or body-size budgets."""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING, final

from typing_extensions import override

from slopgate.constants import (
    MAX_GOD_CLASS_LINES,
    METADATA_PATH,
    PERMISSION_REQUEST,
    POST_TOOL_USE,
    PRE_TOOL_USE,
)
from slopgate.lint._helpers import class_body_lines
from slopgate.models import RuleFinding, Severity
from slopgate.rules.base import Rule
from ..._helpers import decision_for_context

if TYPE_CHECKING:
    from slopgate.context import HookContext
from ..module import python_structural_sources
from ..source_parse import parsed_classes, python_ast_rule_is_disabled


@final
class PythonGodClassRule(Rule):
    """PY-CODE-014: Block god classes by method count or class body size."""

    rule_id = "PY-CODE-014"
    title = "Block god class"
    events = (PRE_TOOL_USE, PERMISSION_REQUEST, POST_TOOL_USE)

    @staticmethod
    def _non_dunder_method_count(node: ast.ClassDef) -> int:
        """Return count of non-dunder methods in a class body."""
        count = 0
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not (child.name.startswith("__") and child.name.endswith("__")):
                    count += 1
        return count

    def _check_source(
        self, source: str, path_value: str, ctx: HookContext
    ) -> list[RuleFinding]:
        findings: list[RuleFinding] = []
        method_limit = ctx.config.python_max_god_class_methods
        line_limit = MAX_GOD_CLASS_LINES
        for node in parsed_classes(source, ctx):
            method_count = self._non_dunder_method_count(node)
            body_lines = class_body_lines(node)
            reasons: list[str] = []
            if method_count > method_limit:
                reasons.append(f"methods={method_count} (limit={method_limit})")
            if body_lines > line_limit:
                reasons.append(f"lines={body_lines} (limit={line_limit})")
            if not reasons:
                continue
            findings.append(
                RuleFinding(
                    rule_id=self.rule_id,
                    title=self.title,
                    severity=Severity.HIGH,
                    decision=decision_for_context(ctx),
                    message=(
                        f"Class `{node.name}` in `{path_value}` is a "
                        f"god-class: {', '.join(reasons)}. Split "
                        "responsibilities before writing it."
                    ),
                    metadata={
                        METADATA_PATH: path_value,
                        "class": node.name,
                        "collector": "god-class",
                        "method_count": method_count,
                        "method_limit": method_limit,
                        "body_lines": body_lines,
                        "line_limit": line_limit,
                    },
                )
            )
        return findings

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if python_ast_rule_is_disabled(ctx, self.rule_id):
            return []
        findings: list[RuleFinding] = []
        for path_value, source in python_structural_sources(ctx):
            findings.extend(self._check_source(source, path_value, ctx))
        return findings
