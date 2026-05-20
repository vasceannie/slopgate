"""Python AST runtime rules."""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING, final
from typing_extensions import override
from vibeforcer.constants import (
    PERMISSION_REQUEST,
    POST_TOOL_USE,
    PRE_TOOL_USE,
    METADATA_PATH,
)
from vibeforcer.models import RuleFinding, Severity
from vibeforcer.rules.base import Rule, is_rule_enabled
from .._helpers import (
    decision_for_context,
    evaluate_common,
    parse_module,
)
if TYPE_CHECKING:
    from vibeforcer.context import HookContext


def _is_broad_exception(handler: ast.ExceptHandler) -> bool:
    exc_type = handler.type
    if exc_type is None:
        return True
    if isinstance(exc_type, ast.Name):
        return exc_type.id in {"Exception", "BaseException"}
    if isinstance(exc_type, ast.Tuple):
        return any(
            isinstance(item, ast.Name) and item.id in {"Exception", "BaseException"}
            for item in exc_type.elts
        )
    return False


def _is_logger_call(node: ast.AST) -> bool:
    match node:
        case ast.Call(func=ast.Attribute(value=ast.Name(id=name))):
            return name in {"logger", "logging"}
        case ast.Call(func=ast.Attribute(attr=method)):
            return method in {"error", "warning", "warn", "exception", "info"}
    return False

def _is_empty_default_return(node: ast.Return) -> bool:
    value = node.value
    if value is None:
        return True
    if isinstance(value, ast.Constant):
        return value.value in {None, False, ""}
    if isinstance(value, ast.List):
        return len(value.elts) == 0
    if isinstance(value, ast.Dict):
        return len(value.keys) == 0
    return False


@final
class PythonBroadExceptLoggerRule(Rule):
    rule_id = "PY-EXC-001"
    title = "Block broad exception handler"
    events = (PRE_TOOL_USE, PERMISSION_REQUEST, POST_TOOL_USE)

    def _check_source(
        self, source: str, path_value: str, ctx: HookContext
    ) -> list[RuleFinding]:
        module = parse_module(source, ctx.config.python_ast_max_parse_chars)
        if module is None:
            return []
        for node in ast.walk(module):
            if not isinstance(node, ast.Try):
                continue
            for handler in node.handlers:
                if not _is_broad_exception(handler):
                    continue
                has_logger = any(_is_logger_call(inner) for stmt in handler.body for inner in ast.walk(stmt))
                has_raise = any(isinstance(inner, ast.Raise) for stmt in handler.body for inner in ast.walk(stmt))
                if has_logger and not has_raise:
                    return [
                        RuleFinding(
                            rule_id=self.rule_id,
                            title=self.title,
                            severity=Severity.HIGH,
                            decision=decision_for_context(ctx),
                            message=(
                                f"Broad exception handler in `{path_value}` logs without re-raising. "
                                "Catch specific exceptions or propagate with context."
                            ),
                            metadata={METADATA_PATH: path_value},
                        )
                    ]
        return []

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        return evaluate_common(self, ctx, self._check_source)


@final
class PythonSilentExceptRule(Rule):
    rule_id = "PY-EXC-002"
    title = "Block silent exception swallow"
    events = (PRE_TOOL_USE, PERMISSION_REQUEST, POST_TOOL_USE)

    def _check_source(
        self, source: str, path_value: str, ctx: HookContext
    ) -> list[RuleFinding]:
        module = parse_module(source, ctx.config.python_ast_max_parse_chars)
        if module is None:
            return []
        for node in ast.walk(module):
            if not isinstance(node, ast.Try):
                continue
            for handler in node.handlers:
                if not _is_broad_exception(handler):
                    continue
                for stmt in handler.body:
                    if isinstance(stmt, (ast.Pass, ast.Continue)):
                        return [
                            RuleFinding(
                                rule_id=self.rule_id,
                                title=self.title,
                                severity=Severity.HIGH,
                                decision=decision_for_context(ctx),
                                message=f"Silent broad exception swallow in `{path_value}`.",
                                metadata={METADATA_PATH: path_value},
                            )
                        ]
                    if isinstance(stmt, ast.Return) and _is_empty_default_return(stmt):
                        return [
                            RuleFinding(
                                rule_id=self.rule_id,
                                title=self.title,
                                severity=Severity.HIGH,
                                decision=decision_for_context(ctx),
                                message=(
                                    f"Broad exception handler in `{path_value}` returns an empty default."
                                ),
                                metadata={METADATA_PATH: path_value},
                            )
                        ]
        return []

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        return evaluate_common(self, ctx, self._check_source)
