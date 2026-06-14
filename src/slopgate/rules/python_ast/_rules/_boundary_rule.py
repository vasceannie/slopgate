"""Python AST runtime rules."""

from __future__ import annotations
from typing import TYPE_CHECKING
from typing_extensions import override
from slopgate.constants import (
    PERMISSION_REQUEST,
    POST_TOOL_USE,
    PRE_TOOL_USE,
    METADATA_FUNCTION,
    METADATA_PATH,
)
from slopgate.models import RuleFinding, Severity
from slopgate.rules.base import Rule, is_rule_enabled
from .._helpers import decision_for_context, evaluate_common, parse_module

if TYPE_CHECKING:
    from slopgate.context import HookContext
from ._boundary_helpers import (
    BoundaryFunction,
    boundary_kind_for_function,
    has_boundary_log_call,
    is_test_module_path,
    iter_public_boundary_functions,
)


class PythonBoundaryLoggingRule(Rule):
    """Require observability at event and package boundaries."""

    rule_id = "PY-LOG-002"
    title = "Require boundary logging"
    events = (PRE_TOOL_USE, PERMISSION_REQUEST, POST_TOOL_USE)

    @staticmethod
    def _boundary_context(ctx: HookContext) -> str:
        snippets = [
            "Boundary logging required: use the project logger/telemetry abstraction, "
            "not stdlib logging. For TUI/Textual lifecycle methods and package/event "
            "boundaries, import the logger factory or telemetry client your project "
            "already provides; define a module logger such as "
            "`logger = get_project_logger(__name__)` when that matches your project "
            "abstraction; then call `logger.info(...)` with "
            "operation/state/count/status fields before the handoff. Include event "
            "name, target package/service, correlation/request id when available, "
            "and enough stable fields to debug failures without logging secrets or "
            "raw payloads.",
        ]
        if ctx.config.hook_project_logger_import:
            snippets.append(f"Project logger import: `{ctx.config.hook_project_logger_import}`.")
        if ctx.config.hook_project_logger_usage:
            snippets.append(f"Project logger usage: `{ctx.config.hook_project_logger_usage}`.")
        return " ".join(snippets)

    def finding(
        self, ctx: HookContext, path_value: str, boundary: BoundaryFunction
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
                f"Python {boundary.kind} `{owner}` in `{path_value}` crosses an "
                "observable boundary without a logging/telemetry call. Add "
                "structured logging before the event/package handoff."
            ),
            additional_context=self._boundary_context(ctx),
            metadata={
                METADATA_PATH: path_value,
                METADATA_FUNCTION: owner,
                "kind": boundary.kind,
                "line": boundary.node.lineno,
            },
        )

    def grouped_finding(
        self, ctx: HookContext, path_value: str, boundaries: list[BoundaryFunction]
    ) -> RuleFinding:
        if len(boundaries) == 1:
            return self.finding(ctx, path_value, boundaries[0])
        owners = [
            f"{boundary.class_name}.{boundary.node.name}"
            if boundary.class_name
            else boundary.node.name
            for boundary in boundaries
        ]
        first_boundary = boundaries[0]
        file_name = path_value.rsplit("/", maxsplit=1)[-1]
        return RuleFinding(
            rule_id=self.rule_id,
            title=self.title,
            severity=Severity.HIGH,
            decision=decision_for_context(ctx),
            message=(
                f"{len(boundaries)} boundaries in {file_name} need structured "
                "logging. "
                "Add a module-level logger and log before the exported boundary "
                f"methods: {', '.join(owners)}."
            ),
            additional_context=self._boundary_context(ctx),
            metadata={
                METADATA_PATH: path_value,
                METADATA_FUNCTION: owners[0],
                "line": first_boundary.node.lineno,
                "kind": first_boundary.kind,
                "functions": owners,
                "lines": [boundary.node.lineno for boundary in boundaries],
                "kinds": [boundary.kind for boundary in boundaries],
                "boundary_count": len(boundaries),
            },
        )

    def _check_source(
        self, source: str, path_value: str, ctx: HookContext
    ) -> list[RuleFinding]:
        if is_test_module_path(path_value):
            return []
        module = parse_module(source, ctx.config.python_ast_max_parse_chars)
        if module is None:
            return []
        boundaries: list[BoundaryFunction] = []
        for node, class_name in iter_public_boundary_functions(module.body):
            kind = boundary_kind_for_function(path_value, node, class_name)
            if kind is None:
                continue
            if has_boundary_log_call(node):
                continue
            boundary = BoundaryFunction(
                node=node,
                kind=kind,
                class_name=class_name,
            )
            boundaries.append(boundary)
        if not boundaries:
            return []
        return [self.grouped_finding(ctx, path_value, boundaries)]

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        return evaluate_common(self, ctx, self._check_source)
