"""Python AST runtime rules."""

from __future__ import annotations
import ast
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
from .._helpers import evaluate_common

if TYPE_CHECKING:
    from slopgate.context import HookContext
from ._source_parse import parsed_functions


class PythonFeatureEnvyRule(Rule):
    """PY-CODE-012: Detect functions where >60% of attribute accesses target one external object."""

    rule_id = "PY-CODE-012"
    title = "Feature envy advisory"
    events = (PRE_TOOL_USE, PERMISSION_REQUEST, POST_TOOL_USE)
    _IGNORE_NAMES = frozenset(
        {
            "os",
            "sys",
            "re",
            "io",
            "abc",
            "ast",
            "csv",
            "json",
            "math",
            "time",
            "uuid",
            "enum",
            "copy",
            "gzip",
            "html",
            "http",
            "shutil",
            "signal",
            "socket",
            "string",
            "struct",
            "typing",
            "base64",
            "codecs",
            "hashlib",
            "logging",
            "pathlib",
            "secrets",
            "sqlite3",
            "urllib",
            "asyncio",
            "collections",
            "contextlib",
            "dataclasses",
            "datetime",
            "functools",
            "importlib",
            "itertools",
            "multiprocessing",
            "operator",
            "platform",
            "pprint",
            "random",
            "subprocess",
            "tempfile",
            "textwrap",
            "threading",
            "traceback",
            "unittest",
            "warnings",
            "np",
            "pd",
            "plt",
            "tf",
            "torch",
            "sk",
            "Path",
            "Enum",
            "Optional",
            "Union",
            "List",
            "Dict",
            "Set",
            "Tuple",
        }
    )

    @staticmethod
    def _root_name(node: ast.Attribute) -> str | None:
        """Walk down the Attribute chain to find the root Name."""
        current: ast.AST = node.value
        while isinstance(current, ast.Attribute):
            current = current.value
        if isinstance(current, ast.Name):
            return current.id
        return None

    @staticmethod
    def _param_names(
        func_node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> frozenset[str]:
        """Collect all parameter names from a function signature."""
        names: list[str] = []
        for arg in (
            func_node.args.args + func_node.args.posonlyargs + func_node.args.kwonlyargs
        ):
            names.append(arg.arg)
        if func_node.args.vararg:
            names.append(func_node.args.vararg.arg)
        if func_node.args.kwarg:
            names.append(func_node.args.kwarg.arg)
        return frozenset(names)

    def _count_envy_accesses(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, param_ns: frozenset[str]
    ) -> tuple[dict[str, int], int]:
        """Count attribute accesses per external object in node."""
        counts: dict[str, int] = {}
        total = 0
        for child in ast.walk(node):
            if not isinstance(child, ast.Attribute):
                continue
            root = self._root_name(child)
            if root is None or root in ("self", "cls") or root in self._IGNORE_NAMES:
                continue
            if root in param_ns:
                continue
            counts[root] = counts.get(root, 0) + 1
            total += 1
        return (counts, total)

    def _check_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        path_value: str,
        ctx: HookContext,
    ) -> RuleFinding | None:
        """Return a finding if node exhibits feature envy, else None."""
        param_ns = self._param_names(node)
        counts, total = self._count_envy_accesses(node, param_ns)
        if total < ctx.config.python_feature_envy_min_accesses:
            return None
        for obj_name, count in counts.items():
            if count / total > ctx.config.python_feature_envy_threshold:
                return RuleFinding(
                    rule_id=self.rule_id,
                    title=self.title,
                    severity=Severity.LOW,
                    decision="context",
                    message=(
                        f"Feature envy: {path_value}:{node.name} overuses "
                        f"{obj_name} ({count}/{total} attrs)."
                    ),
                    metadata={
                        METADATA_PATH: path_value,
                        METADATA_FUNCTION: node.name,
                        "envied_object": obj_name,
                        "accesses": count,
                        "total": total,
                    },
                )
        return None

    def _check_source(
        self, source: str, path_value: str, ctx: HookContext
    ) -> list[RuleFinding]:
        findings: list[RuleFinding] = []
        for node in parsed_functions(source, ctx):
            finding = self._check_function(node, path_value, ctx)
            if finding is not None:
                findings.append(finding)
        return findings

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        return evaluate_common(self, ctx, self._check_source)
