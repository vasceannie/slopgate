"""Detect Python functions whose body is a single delegating call."""

from __future__ import annotations

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
from .calls import (
    is_exempt_cast_wrapper,
    is_exempt_test_helper_wrapper,
    is_wrapper_candidate,
    thin_wrapper_call_target_name,
    thin_wrapper_extract_single_call,
)


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
        for node in parsed_functions(source, ctx):
            if not is_wrapper_candidate(node):
                continue
            call_node = thin_wrapper_extract_single_call(node.body[0])
            if call_node is None:
                continue
            if is_exempt_cast_wrapper(call_node):
                continue
            if is_exempt_test_helper_wrapper(node, call_node, path_value):
                continue
            wrapped = thin_wrapper_call_target_name(call_node)
            findings.append(
                RuleFinding(
                    rule_id=self.rule_id,
                    title=self.title,
                    severity=Severity.MEDIUM,
                    decision=decision_for_context(ctx),
                    message=(
                        f"Function `{node.name}` at `{path_value}` is a thin "
                        f"wrapper around `{wrapped}`. Consider calling the "
                        "wrapped function directly."
                    ),
                    metadata={
                        METADATA_PATH: path_value,
                        METADATA_FUNCTION: node.name,
                        "wraps": wrapped,
                    },
                )
            )
        return findings

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        return evaluate_common(self, ctx, self._check_source)
