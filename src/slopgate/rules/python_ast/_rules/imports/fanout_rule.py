"""Python AST runtime rules."""

from __future__ import annotations

import ast
from collections import defaultdict
from typing import TYPE_CHECKING
from typing_extensions import override
from slopgate.constants import (
    PERMISSION_REQUEST,
    POST_TOOL_USE,
    PRE_TOOL_USE,
    IMPORT_FANOUT_PREVIEW_LIMIT,
    METADATA_PATH,
)
from slopgate.models import RuleFinding, Severity
from slopgate.rules.base import Rule, is_rule_enabled
from ..._helpers import detect_family_prefix, evaluate_common, parse_module

if TYPE_CHECKING:
    from slopgate.context import HookContext


class PythonImportFanoutRule(Rule):
    """PY-IMPORT-001: Detect when too many names are imported from one module.

    A high import count from a single module signals that the caller should
    either use a namespace import or that the source module needs a facade.
    """

    rule_id = "PY-IMPORT-001"
    title = "Import fanout suggests facade opportunity"
    events = (PRE_TOOL_USE, PERMISSION_REQUEST, POST_TOOL_USE)

    @staticmethod
    def _collect_names_by_module(module: ast.Module) -> dict[str, list[str]]:
        """Return mapping of source-module name -> imported names (top-level only)."""
        names_by_module: dict[str, list[str]] = defaultdict(list)
        for node in module.body:
            if not isinstance(node, ast.ImportFrom) or node.module is None:
                continue
            for alias in node.names:
                imported_name = alias.asname if alias.asname else alias.name
                names_by_module[node.module].append(imported_name)
        return names_by_module

    def _fanout_finding(
        self, path_value: str, mod_name: str, names: list[str], limit: int
    ) -> RuleFinding | None:
        """Return a finding when import count exceeds limit, else None."""
        if len(names) <= limit:
            return None
        family_prefix = detect_family_prefix(names)
        names_preview = ", ".join(names[:IMPORT_FANOUT_PREVIEW_LIMIT]) + (
            ", ..." if len(names) > IMPORT_FANOUT_PREVIEW_LIMIT else ""
        )
        if family_prefix is not None:
            severity = Severity.MEDIUM
            family_msg = (
                f" Several names share the `{family_prefix}` prefix"
                " \u2014 strong signal for a service class or facade."
            )
        else:
            severity = Severity.LOW
            family_msg = ""
        message = (
            f"`{path_value}` imports {len(names)} names from `{mod_name}` "
            f"({names_preview}).{family_msg} Advisory only: this is context "
            "for a future dependency-design pass; do not retry the write solely "
            f"for this. Consider `import {mod_name}` and access via namespace, "
            f"or introduce a facade/service class to reduce coupling when the "
            f"module boundary is already in scope."
        )
        return RuleFinding(
            rule_id=self.rule_id,
            title=self.title,
            severity=severity,
            decision="context",
            message=message,
            metadata={
                METADATA_PATH: path_value,
                "module": mod_name,
                "import_count": len(names),
                "names": names,
                "family_prefix": family_prefix,
            },
        )

    def _check_source(
        self,
        source: str,
        path_value: str,
        ctx: HookContext,
    ) -> list[RuleFinding]:
        module = parse_module(source, ctx.config.python_ast_max_parse_chars)
        if module is None:
            return []
        limit = ctx.config.python_import_fanout_limit
        names_by_module = self._collect_names_by_module(module)
        findings: list[RuleFinding] = []
        for mod_name, names in names_by_module.items():
            finding = self._fanout_finding(path_value, mod_name, names, limit)
            if finding is not None:
                findings.append(finding)
        return findings

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        return evaluate_common(self, ctx, self._check_source)
