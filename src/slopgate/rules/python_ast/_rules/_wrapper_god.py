"""Python AST runtime rules."""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING, final
from typing_extensions import override
from vibeforcer.constants import (
    MAX_GOD_CLASS_LINES,
    PERMISSION_REQUEST,
    POST_TOOL_USE,
    PRE_TOOL_USE,
    METADATA_FUNCTION,
    METADATA_PATH,
)
from vibeforcer.lint._helpers import class_body_lines as _class_body_lines
from vibeforcer.models import RuleFinding, Severity
from vibeforcer.rules.base import Rule, is_rule_enabled
from .._helpers import (
    decision_for_context,
    evaluate_common,
)
if TYPE_CHECKING:
    from vibeforcer.context import HookContext

from ._module_size_projection import _python_structural_sources as _python_structural_sources
from ._source_parse import _parsed_classes as _parsed_classes, _parsed_functions as _parsed_functions, _python_ast_rule_is_disabled as _python_ast_rule_is_disabled


def _thin_wrapper_extract_single_call(stmt: ast.stmt) -> ast.Call | None:
    """Return the Call node if stmt is a single-statement Return/Expr call."""
    match stmt:
        case ast.Return(value=ast.Call() as call_node):
            return call_node
        case ast.Expr(value=ast.Call() as call_node):
            return call_node
    return None


def _thin_wrapper_attribute_name(node: ast.Attribute) -> str:
    parts: list[str] = [node.attr]
    current: ast.expr = node.value
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
    else:
        return node.attr
    return ".".join(reversed(parts))


def _thin_wrapper_call_target_name(call_node: ast.Call) -> str:
    func = call_node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return _thin_wrapper_attribute_name(func)
    return "<unknown>"


def _thin_wrapper_call_root_name(call_node: ast.Call) -> str | None:
    match call_node.func:
        case ast.Name(id=name):
            return name
        case ast.Attribute() as attr:
            current: ast.expr = attr.value
            while isinstance(current, ast.Attribute):
                current = current.value
            if isinstance(current, ast.Name):
                return current.id
    return None


def _thin_wrapper_has_self_or_cls_receiver(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    call_node: ast.Call,
) -> bool:
    if not node.args.args:
        return False
    receiver_name = node.args.args[0].arg
    if receiver_name not in {"self", "cls"}:
        return False
    return _thin_wrapper_call_root_name(call_node) == receiver_name


def _is_test_helper_path(path_value: str) -> bool:
    normalized = path_value.replace("\\", "/").lower()
    return (
        normalized.startswith("tests/")
        or "/tests/" in normalized
        or normalized.endswith("/conftest.py")
        or normalized == "conftest.py"
    )


def _is_exempt_cast_wrapper(call_node: ast.Call) -> bool:
    return isinstance(call_node.func, ast.Name) and call_node.func.id == "cast"


def _is_exempt_test_helper_wrapper(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    call_node: ast.Call,
    path_value: str,
) -> bool:
    if not _is_test_helper_path(path_value):
        return False
    if isinstance(call_node.func, ast.Name) and call_node.func.id in {"list", "cast"}:
        return True
    return _thin_wrapper_has_self_or_cls_receiver(node, call_node)


def _is_wrapper_candidate(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> bool:
    """Return True when node is a non-dunder, undecorated single-statement function."""
    if node.name.startswith("__") and node.name.endswith("__"):
        return False
    if node.decorator_list:
        return False
    return len(node.body) == 1


@final
class PythonThinWrapperRule(Rule):
    """PY-CODE-013: Detect functions whose body is a single delegating call."""

    rule_id = "PY-CODE-013"
    title = "Block thin wrappers"
    events = (PRE_TOOL_USE, PERMISSION_REQUEST, POST_TOOL_USE)

    def _check_source(
        self, source: str, path_value: str, ctx: HookContext
    ) -> list[RuleFinding]:
        findings: list[RuleFinding] = []
        for node in _parsed_functions(source, ctx):
            if not _is_wrapper_candidate(node):
                continue
            call_node = _thin_wrapper_extract_single_call(node.body[0])
            if call_node is None:
                continue
            if _is_exempt_cast_wrapper(call_node):
                continue
            if _is_exempt_test_helper_wrapper(node, call_node, path_value):
                continue
            wrapped = _thin_wrapper_call_target_name(call_node)
            findings.append(RuleFinding(
                rule_id=self.rule_id,
                title=self.title,
                severity=Severity.MEDIUM,
                decision=decision_for_context(ctx),
                message=(
                    f"Function `{node.name}` in `{path_value}` is a thin wrapper "
                    f"around `{wrapped}`. Consider calling the wrapped function directly."
                ),
                metadata={METADATA_PATH: path_value, METADATA_FUNCTION: node.name, "wraps": wrapped},
            ))
        return findings

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        return evaluate_common(self, ctx, self._check_source)


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
        for node in _parsed_classes(source, ctx):
            method_count = self._non_dunder_method_count(node)
            body_lines = _class_body_lines(node)
            reasons: list[str] = []
            if method_count > method_limit:
                reasons.append(f"methods={method_count} (limit={method_limit})")
            if body_lines > line_limit:
                reasons.append(f"lines={body_lines} (limit={line_limit})")
            if not reasons:
                continue
            findings.append(RuleFinding(
                rule_id=self.rule_id,
                title=self.title,
                severity=Severity.HIGH,
                decision=decision_for_context(ctx),
                message=(
                    f"Class `{node.name}` in `{path_value}` is a god-class: "
                    f"{', '.join(reasons)}. Split responsibilities before writing it."
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
            ))
        return findings

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if _python_ast_rule_is_disabled(ctx, self.rule_id):
            return []
        findings: list[RuleFinding] = []
        for path_value, source in _python_structural_sources(ctx):
            findings.extend(self._check_source(source, path_value, ctx))
        return findings
