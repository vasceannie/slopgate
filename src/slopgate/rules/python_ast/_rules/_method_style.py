"""Python AST runtime rules."""

from __future__ import annotations

import ast
import io
import tokenize
from typing import TYPE_CHECKING, final
from typing_extensions import override
from vibeforcer.constants import (
    DENY,
    PERMISSION_REQUEST,
    POST_TOOL_USE,
    PRE_TOOL_USE,
    BLOCK,
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

from ._source_parse import _parse_strict as _parse_strict, _parsed_functions as _parsed_functions


class PythonLongMethodRule(Rule):
    rule_id = "PY-CODE-008"
    title = "Block long Python methods"
    events = (PRE_TOOL_USE, PERMISSION_REQUEST, POST_TOOL_USE)

    @staticmethod
    def _worst_function(module: ast.Module, limit: int) -> tuple[str, int] | None:
        """Return (name, span) of the longest over-limit function, or None."""
        worst: tuple[str, int] | None = None
        for node in ast.walk(module):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.end_lineno is None:
                continue
            span = node.end_lineno - node.lineno + 1
            if span > limit and (worst is None or span > worst[1]):
                worst = (node.name, span)
        return worst

    def _check_source(
        self, source: str, path_value: str, ctx: HookContext
    ) -> list[RuleFinding]:
        """Return findings for any too-long functions in source."""
        module = _parse_strict(source, ctx.config.python_ast_max_parse_chars)
        if module is None:
            return []
        worst = self._worst_function(module, ctx.config.python_long_method_lines)
        if worst is None:
            return []
        name, span = worst
        limit = ctx.config.python_long_method_lines
        decision = (
            DENY if ctx.event_name in (PRE_TOOL_USE, PERMISSION_REQUEST) else BLOCK
        )
        return [RuleFinding(
            rule_id=self.rule_id,
            title=self.title,
            severity=Severity.HIGH,
            decision=decision,
            message=(
                f"Python function `{name}` in `{path_value}` is {span} lines long. "
                f"Keep functions under {limit} lines or split them into helpers."
            ),
            metadata={METADATA_PATH: path_value, METADATA_FUNCTION: name, "lines": span},
        )]

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        return evaluate_common(self, ctx, self._check_source)


@final
class PythonLongParameterRule(Rule):
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
        module = _parse_strict(source, ctx.config.python_ast_max_parse_chars)
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
        return [RuleFinding(
            rule_id=self.rule_id,
            title=self.title,
            severity=Severity.MEDIUM,
            decision=decision,
            message=(
                f"Python function `{name}` in `{path_value}` declares {count} parameters. "
                f"Keep functions at or below {limit} parameters or group inputs into objects."
            ),
            metadata={METADATA_PATH: path_value, METADATA_FUNCTION: name, "parameter_count": count},
        )]

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        return evaluate_common(self, ctx, self._check_source)


# ---------------------------------------------------------------------------
# New rules (PY-CODE-010 through PY-CODE-016)
# ---------------------------------------------------------------------------


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
        return worst_lineno, worst_length

    def _check_source(
        self, source: str, path_value: str, ctx: HookContext
    ) -> list[RuleFinding]:
        max_length = ctx.config.python_max_line_length
        if len(source) > ctx.config.python_ast_max_parse_chars:
            return []
        worst_lineno, worst_length = self._find_worst_line(source, max_length)
        if worst_length <= max_length:
            return []
        return [RuleFinding(
            rule_id=self.rule_id,
            title=self.title,
            severity=Severity.MEDIUM,
            decision=decision_for_context(ctx),
            message=(
                f"Line {worst_lineno} in `{path_value}` is {worst_length} code characters long. "
                f"Keep executable code lines at or below {max_length} characters. "
                "Docstrings/string literals and whitespace-only padding are ignored; "
                "wrap the expression or extract an intermediate variable instead of "
                "mangling docs or spacing."
            ),
            metadata={METADATA_PATH: path_value, "line": worst_lineno, "length": worst_length},
        )]

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        return evaluate_common(self, ctx, self._check_source)


@final
class PythonDeepNestingRule(Rule):
    """PY-CODE-011: Block functions with nesting depth > 4."""

    rule_id = "PY-CODE-011"
    title = "Block deep nesting"
    events = (PRE_TOOL_USE, PERMISSION_REQUEST, POST_TOOL_USE)

    _NESTING_TYPES = (
        ast.If,
        ast.For,
        ast.While,
        ast.AsyncFor,
        ast.With,
        ast.AsyncWith,
        ast.Try,
        ast.ExceptHandler,
    )

    def _max_nesting(self, node: ast.AST, depth: int = 0) -> int:
        """Return the maximum nesting depth below node."""
        max_d = depth
        for child in ast.iter_child_nodes(node):
            if isinstance(child, self._NESTING_TYPES):
                max_d = max(max_d, self._max_nesting(child, depth + 1))
            else:
                max_d = max(max_d, self._max_nesting(child, depth))
        return max_d

    def _check_source(
        self, source: str, path_value: str, ctx: HookContext
    ) -> list[RuleFinding]:
        worst_name = ""
        worst_depth = 0
        for node in _parsed_functions(source, ctx):
            depth = self._max_nesting(node, 0)
            if depth > ctx.config.python_max_nesting_depth and depth > worst_depth:
                worst_name = node.name
                worst_depth = depth
        if not worst_name:
            return []
        limit = ctx.config.python_max_nesting_depth
        return [RuleFinding(
            rule_id=self.rule_id,
            title=self.title,
            severity=Severity.HIGH,
            decision=decision_for_context(ctx),
            message=(
                f"Function `{worst_name}` in `{path_value}` has nesting depth {worst_depth}. "
                f"Keep nesting at or below {limit} levels."
            ),
            metadata={METADATA_PATH: path_value, METADATA_FUNCTION: worst_name, "depth": worst_depth},
        )]

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        return evaluate_common(self, ctx, self._check_source)
