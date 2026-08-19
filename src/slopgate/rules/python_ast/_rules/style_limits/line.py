"""Detect Python source lines that exceed the configured character budget."""

from __future__ import annotations

import io
import tokenize
from typing import TYPE_CHECKING, final

from typing_extensions import override

from slopgate.constants import (
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


@final
class PythonLongLineRule(Rule):
    """PY-CODE-010: Block files containing lines over 120 characters."""

    rule_id = "PY-CODE-010"
    title = "Block long lines"
    events = (PRE_TOOL_USE, PERMISSION_REQUEST, POST_TOOL_USE)

    @staticmethod
    def _string_literal_lines(source: str) -> set[int]:
        """Return physical lines occupied by string literals/docstrings."""
        lines: set[int] = set()
        try:
            tokens = tokenize.generate_tokens(io.StringIO(source).readline)
            for token in tokens:
                if token.type != tokenize.STRING:
                    continue
                start_line = token.start[0]
                end_line = token.end[0]
                lines.update(range(start_line, end_line + 1))
        except tokenize.TokenError:
            return lines
        return lines

    def _find_worst_line(self, source: str, max_length: int) -> tuple[int, int]:
        """Scan source and return (lineno, length) of the longest offending line."""
        string_lines = self._string_literal_lines(source)
        worst_lineno = 0
        worst_length = 0
        for lineno, raw_line in enumerate(source.splitlines(), start=1):
            stripped = raw_line.strip()
            if not stripped:
                continue
            if lineno in string_lines or stripped.startswith("#"):
                continue
            if stripped.startswith("import ") or stripped.startswith("from "):
                continue
            if "http://" in raw_line or "https://" in raw_line:
                continue
            code_length = len(raw_line.rstrip())
            if code_length > max_length and code_length > worst_length:
                worst_lineno = lineno
                worst_length = code_length
        return (worst_lineno, worst_length)

    def _check_source(
        self, source: str, path_value: str, ctx: HookContext
    ) -> list[RuleFinding]:
        max_length = ctx.config.python_max_line_length
        if len(source) > ctx.config.python_ast_max_parse_chars:
            return []
        worst_lineno, worst_length = self._find_worst_line(source, max_length)
        if worst_length <= max_length:
            return []
        return [
            RuleFinding(
                rule_id=self.rule_id,
                title=self.title,
                severity=Severity.MEDIUM,
                decision=decision_for_context(ctx),
                message=(
                    f"Line {worst_lineno} in `{path_value}` is {worst_length} "
                    f"code characters long; limit is {max_length}. Wrap or "
                    "extract executable code; docs, strings, and blank padding "
                    "are ignored."
                ),
                metadata={
                    METADATA_PATH: path_value,
                    "line": worst_lineno,
                    "length": worst_length,
                },
            )
        ]

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        return evaluate_common(self, ctx, self._check_source)
