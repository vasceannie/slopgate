"""Python AST runtime rules."""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING
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

from ._import_helpers import _PrivateImportFinding as _PrivateImportFinding, _imported_modules as _imported_modules, _module_path_from_python_file as _module_path_from_python_file, _patch_added_source as _patch_added_source, _private_module_segments as _private_module_segments


class PythonPrivateImportChainRule(Rule):
    """Block stacked private module paths/imports such as _orchestrate._core."""

    rule_id = "PY-IMPORT-003"
    title = "Block stacked private Python import chains"
    events = (PRE_TOOL_USE, PERMISSION_REQUEST, POST_TOOL_USE)

    def _finding(self, ctx: HookContext, finding: _PrivateImportFinding) -> RuleFinding:
        location = f" on line {finding.line}" if finding.line is not None else ""
        return RuleFinding(
            rule_id=self.rule_id,
            title=self.title,
            severity=Severity.HIGH,
            decision=decision_for_context(ctx),
            message=(
                f"`{finding.path_value}` introduces a stacked private Python "
                f"{finding.kind}{location}: `{finding.target}`. Avoid names that force "
                "imports like `pkg._impl._core`; expose the API through a facade "
                "or use descriptive public module names."
            ),
            additional_context=(
                "Keep at most one private module segment in an import/path. If a split "
                "needs multiple files, prefer `orchestrate/context.py`, "
                "`orchestrate/platform_auth.py`, etc., and re-export stable names from "
                "the package boundary instead of making callers import nested internals."
            ),
            metadata={
                METADATA_PATH: finding.path_value,
                "target": finding.target,
                "kind": finding.kind,
                "line": finding.line,
            },
        )

    def _path_finding(self, ctx: HookContext, path_value: str) -> RuleFinding | None:
        module_path = _module_path_from_python_file(path_value)
        if len(_private_module_segments(module_path)) < 2:
            return None
        return self._finding(
            ctx,
            _PrivateImportFinding(
                path_value=path_value,
                target=module_path,
                kind="module path",
            ),
        )

    def _import_findings(
        self,
        ctx: HookContext,
        source: str,
        path_value: str,
    ) -> list[RuleFinding]:
        module = parse_module(source, ctx.config.python_ast_max_parse_chars)
        if module is None:
            added_source = _patch_added_source(source)
            module = parse_module(added_source or "", ctx.config.python_ast_max_parse_chars)
        if module is None:
            return []
        findings: list[RuleFinding] = []
        for node in ast.walk(module):
            for line, module_name in _imported_modules(node):
                if len(_private_module_segments(module_name)) < 2:
                    continue
                findings.append(
                    self._finding(
                        ctx,
                        _PrivateImportFinding(
                            path_value=path_value,
                            target=module_name,
                            kind="import chain",
                            line=line,
                        ),
                    )
                )
        return findings

    def _check_source(
        self,
        source: str,
        path_value: str,
        ctx: HookContext,
    ) -> list[RuleFinding]:
        findings: list[RuleFinding] = []
        path_finding = self._path_finding(ctx, path_value)
        if path_finding is not None:
            findings.append(path_finding)
        findings.extend(self._import_findings(ctx, source, path_value))
        return findings

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        return evaluate_common(self, ctx, self._check_source)
