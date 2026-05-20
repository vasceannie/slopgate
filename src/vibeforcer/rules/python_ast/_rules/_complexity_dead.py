"""Python AST runtime rules."""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING, final
from typing_extensions import override
from vibeforcer.constants import (
    PERMISSION_REQUEST,
    POST_TOOL_USE,
    PRE_TOOL_USE,
    METADATA_FUNCTION,
    METADATA_PATH,
)
from vibeforcer.models import RuleFinding, Severity
from vibeforcer.rules.base import Rule, is_rule_enabled
from .._helpers import (
    decision_for_context,
    evaluate_common,
)
if TYPE_CHECKING:
    from vibeforcer.context import HookContext

from ._source_parse import _parsed_functions as _parsed_functions


_CC_BRANCH_TYPES = (
    ast.If,
    ast.IfExp,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.ExceptHandler,
    ast.With,
    ast.AsyncWith,
    ast.Assert,
    ast.comprehension,
)


@final
class PythonCyclomaticComplexityRule(Rule):
    """PY-CODE-015: Block functions with cyclomatic complexity > 10."""

    rule_id = "PY-CODE-015"
    title = "Block cyclomatic complexity"
    events = (PRE_TOOL_USE, PERMISSION_REQUEST, POST_TOOL_USE)

    @staticmethod
    def _complexity(node: ast.AST) -> int:
        """Compute cyclomatic complexity for a function body."""
        complexity = 1
        for child in ast.walk(node):
            if isinstance(child, _CC_BRANCH_TYPES):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
        return complexity

    def _check_source(
        self, source: str, path_value: str, ctx: HookContext
    ) -> list[RuleFinding]:
        worst_name = ""
        worst_cc = 0
        for node in _parsed_functions(source, ctx):
            cc = self._complexity(node)
            if cc > ctx.config.python_max_complexity and cc > worst_cc:
                worst_name = node.name
                worst_cc = cc
        if not worst_name:
            return []
        limit = ctx.config.python_max_complexity
        return [RuleFinding(
            rule_id=self.rule_id,
            title=self.title,
            severity=Severity.HIGH,
            decision=decision_for_context(ctx),
            message=(
                f"Function `{worst_name}` in `{path_value}` has cyclomatic complexity {worst_cc}. "
                f"Keep complexity at or below {limit}."
            ),
            metadata={METADATA_PATH: path_value, METADATA_FUNCTION: worst_name, "complexity": worst_cc},
        )]

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        return evaluate_common(self, ctx, self._check_source)


@final
class PythonDeadCodeRule(Rule):
    """PY-CODE-016: Detect unreachable code after return/raise/break/continue."""

    rule_id = "PY-CODE-016"
    title = "Block dead code after return"
    events = (PRE_TOOL_USE, PERMISSION_REQUEST, POST_TOOL_USE)

    _TERMINAL = (ast.Return, ast.Raise, ast.Break, ast.Continue)

    def _scan_block(self, stmts: list[ast.stmt]) -> tuple[str | None, int]:
        """Return (description, lineno) of first dead statement, or (None, 0)."""
        for i, stmt in enumerate(stmts):
            if isinstance(stmt, self._TERMINAL) and i < len(stmts) - 1:
                dead_stmt = stmts[i + 1]
                return (type(stmt).__name__.lower(), getattr(dead_stmt, "lineno", 0))
        return (None, 0)

    @staticmethod
    def _collect_blocks(child: ast.AST) -> list[list[ast.stmt]]:
        """Return all statement blocks owned by child that should be scanned."""
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return [child.body]
        if isinstance(child, (ast.If, ast.For, ast.AsyncFor, ast.While)):
            blocks: list[list[ast.stmt]] = [child.body]
            if child.orelse:
                blocks.append(child.orelse)
            return blocks
        if isinstance(child, ast.Try):
            blocks = [child.body]
            for handler in child.handlers:
                blocks.append(handler.body)
            if child.orelse:
                blocks.append(child.orelse)
            if child.finalbody:
                blocks.append(child.finalbody)
            return blocks
        if isinstance(child, (ast.With, ast.AsyncWith, ast.ExceptHandler)):
            return [child.body]
        return []

    def _find_dead_code(self, node: ast.AST) -> list[tuple[str, int]]:
        """Walk all statement blocks and collect dead code locations."""
        results: list[tuple[str, int]] = []
        for child in ast.walk(node):
            for block in self._collect_blocks(child):
                cause, lineno = self._scan_block(block)
                if cause is not None:
                    results.append((cause, lineno))
        return results

    def _check_source(
        self, source: str, path_value: str, ctx: HookContext
    ) -> list[RuleFinding]:
        findings: list[RuleFinding] = []
        for node in _parsed_functions(source, ctx):
            dead = self._find_dead_code(node)
            if not dead:
                continue
            cause, lineno = dead[0]
            findings.append(RuleFinding(
                rule_id=self.rule_id,
                title=self.title,
                severity=Severity.HIGH,
                decision=decision_for_context(ctx),
                message=(
                    f"Function `{node.name}` in `{path_value}` has unreachable code "
                    f"after `{cause}` at line {lineno}."
                ),
                metadata={
                    METADATA_PATH: path_value,
                    METADATA_FUNCTION: node.name,
                    "dead_line": lineno,
                    "cause": cause,
                },
            ))
        return findings

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        return evaluate_common(self, ctx, self._check_source)
