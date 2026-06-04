"""Python AST runtime rules."""

from __future__ import annotations

import shlex
from typing import TYPE_CHECKING
from typing_extensions import override
from slopgate.constants import (
    LINT_MAX_MODULE_LINES_SOFT,
    PERMISSION_REQUEST,
    POST_TOOL_USE,
    PRE_TOOL_USE,
    METADATA_PATH,
)
from slopgate.models import RuleFinding, Severity
from slopgate.rules.base import Rule, is_rule_enabled
from slopgate.util.payloads import (
    is_bash_tool,
    is_edit_like_tool,
)
from .._helpers import (
    decision_for_context,
)
if TYPE_CHECKING:
    from slopgate.context import HookContext

from ._module_size_projection import _is_authored_python_path as _is_authored_python_path
from ._source_parse import _is_full_module_candidate as _is_full_module_candidate, _line_count as _line_count, _parse_health_failure as _parse_health_failure, _resolve_python_path as _resolve_python_path


class PythonAstHealthRule(Rule):
    """Emit findings when AST checks cannot run due to parse/read failures."""

    rule_id = "PY-AST-001"
    title = "Python AST parse/read failure"
    events = (PRE_TOOL_USE, PERMISSION_REQUEST, POST_TOOL_USE)

    @staticmethod
    def _recovery_text(path_value: str, kind: str) -> str:
        quoted_path = shlex.quote(path_value)
        if kind == "read_error":
            return (
                f"Next step: verify the path first with `test -e {quoted_path}`; "
                "if it was moved/renamed, re-read the moved/renamed file before "
                "running syntax checks."
            )
        return (
            "Next step: stop refactoring, re-read the whole file, restore syntax, "
            f"then run `python3 -m py_compile {quoted_path}`."
        )

    def _finding(self, ctx: HookContext, path_value: str, kind: str) -> RuleFinding:
        recovery = self._recovery_text(path_value, kind)
        return RuleFinding(
            rule_id=self.rule_id,
            title=self.title,
            severity=Severity.HIGH,
            decision=decision_for_context(ctx),
            message=f"Python AST analysis could not run for `{path_value}` ({kind}). {recovery}",
            additional_context=recovery,
            metadata={METADATA_PATH: path_value, "kind": kind},
        )

    def _pre_content_failure(self, ctx: HookContext, ct: object) -> RuleFinding | None:
        path = getattr(ct, METADATA_PATH)
        if not _is_authored_python_path(path):
            return None
        if not _is_full_module_candidate(ctx, getattr(ct, "source")):
            return None
        failure = _parse_health_failure(
            getattr(ct, "content"),
            ctx.config.python_ast_max_parse_chars,
            suppress_fragments=True,
        )
        if failure == "oversized" and _line_count(getattr(ct, "content")) > LINT_MAX_MODULE_LINES_SOFT:
            return None
        return self._finding(ctx, path, failure) if failure is not None else None

    def _post_path_failure(self, ctx: HookContext, path_value: str) -> RuleFinding | None:
        if not _is_authored_python_path(path_value):
            return None
        full_path = _resolve_python_path(ctx, path_value)
        try:
            source = full_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            if ctx.event_name == POST_TOOL_USE and is_bash_tool(ctx.tool_name):
                return None
            return self._finding(ctx, path_value, "read_error")
        except OSError:
            return self._finding(ctx, path_value, "read_error")
        failure = _parse_health_failure(
            source,
            ctx.config.python_ast_max_parse_chars,
            suppress_fragments=False,
        )
        if failure == "oversized" and _line_count(source) > LINT_MAX_MODULE_LINES_SOFT:
            return None
        return self._finding(ctx, path_value, failure) if failure is not None else None

    def _evaluate_pre(self, ctx: HookContext) -> list[RuleFinding]:
        findings = [self._pre_content_failure(ctx, ct) for ct in ctx.content_targets]
        return [finding for finding in findings if finding is not None]

    def _evaluate_post(self, ctx: HookContext) -> list[RuleFinding]:
        if not (is_edit_like_tool(ctx.tool_name) or is_bash_tool(ctx.tool_name)):
            return []
        findings = [self._post_path_failure(ctx, path) for path in ctx.candidate_paths]
        return [finding for finding in findings if finding is not None]

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        if not ctx.config.python_ast_enabled:
            return []
        if ctx.event_name in (PRE_TOOL_USE, PERMISSION_REQUEST):
            return self._evaluate_pre(ctx)
        return self._evaluate_post(ctx)
