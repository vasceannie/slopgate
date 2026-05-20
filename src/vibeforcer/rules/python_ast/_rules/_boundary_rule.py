"""Python AST runtime rules."""

from __future__ import annotations

from typing import TYPE_CHECKING
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
    parse_module,
)
if TYPE_CHECKING:
    from vibeforcer.context import HookContext

from ._boundary_helpers import _BoundaryFunction as _BoundaryFunction, _boundary_kind_for_function as _boundary_kind_for_function, _has_boundary_log_call as _has_boundary_log_call, _is_test_module_path as _is_test_module_path, _iter_public_boundary_functions as _iter_public_boundary_functions


class PythonBoundaryLoggingRule(Rule):
    """Require observability at event and package boundaries."""

    rule_id = "PY-LOG-002"
    title = "Require boundary logging"
    events = (PRE_TOOL_USE, PERMISSION_REQUEST, POST_TOOL_USE)

    def _finding(
        self,
        ctx: HookContext,
        path_value: str,
        boundary: _BoundaryFunction,
    ) -> RuleFinding:
        owner = (
            f"{boundary.class_name}.{boundary.node.name}"
            if boundary.class_name
            else boundary.node.name
        )
        return RuleFinding(
            rule_id=self.rule_id,
            title=self.title,
            severity=Severity.HIGH,
            decision=decision_for_context(ctx),
            message=(
                f"Python {boundary.kind} `{owner}` in `{path_value}` crosses an observable "
                "boundary without a logging/telemetry call. Add structured logging "
                "before the event/package handoff."
            ),
            additional_context=(
                "Boundary logging required: use the project logger/telemetry "
                "abstraction, not stdlib logging. Prefer `logger.info(...)` with "
                "the event name or target package/service, correlation/request id "
                "when available, and enough stable fields to debug failures without "
                "logging secrets or raw payload bodies."
            ),
            metadata={
                METADATA_PATH: path_value,
                METADATA_FUNCTION: owner,
                "kind": boundary.kind,
                "line": boundary.node.lineno,
            },
        )

    def _check_source(
        self, source: str, path_value: str, ctx: HookContext
    ) -> list[RuleFinding]:
        if _is_test_module_path(path_value):
            return []
        module = parse_module(source, ctx.config.python_ast_max_parse_chars)
        if module is None:
            return []
        findings: list[RuleFinding] = []
        for node, class_name in _iter_public_boundary_functions(module.body):
            kind = _boundary_kind_for_function(path_value, node, class_name)
            if kind is None:
                continue
            if _has_boundary_log_call(node):
                continue
            boundary = _BoundaryFunction(node=node, kind=kind, class_name=class_name)
            findings.append(self._finding(ctx, path_value, boundary))
        return findings

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        return evaluate_common(self, ctx, self._check_source)
