"""Guard against stacked private Python module paths and imports."""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from typing_extensions import override

from slopgate.constants import (
    METADATA_PATH,
    METADATA_LINE,
    METADATA_TARGET,
    PERMISSION_REQUEST,
    POST_TOOL_USE,
    PRE_TOOL_USE,
)
from slopgate.models import RuleFinding, Severity
from slopgate.rules.base import Rule, is_rule_enabled

from .._helpers import decision_for_context, evaluate_common, parse_module
from ._flat_siblings import (
    flat_sibling_patch_added_and_removed_paths,
    flat_sibling_patch_blob,
    flat_sibling_resolve_candidate_path,
)
from .imports import (
    PrivateImportFinding,
    imported_modules,
    module_path_from_python_file,
    patch_added_source,
    private_module_segments,
)

if TYPE_CHECKING:
    from slopgate.context import HookContext


class PythonPrivateImportChainRule(Rule):
    """Block stacked private paths while allowing patches that remove them."""

    rule_id = "PY-IMPORT-003"
    title = "Block stacked private Python import chains"
    events = (PRE_TOOL_USE, PERMISSION_REQUEST, POST_TOOL_USE)

    def finding(self, ctx: HookContext, finding: PrivateImportFinding) -> RuleFinding:
        location = f" on line {finding.line}" if finding.line is not None else ""
        message = (
            f"`{finding.path_value}` introduces a stacked private Python "
            f"{finding.kind}{location}: `{finding.target}`. Avoid names that force "
            "imports like `pkg._impl._core`; expose the API through a facade or use "
            "descriptive public module names."
        )
        additional_context = (
            "Keep at most one private module segment in an import/path. If a split "
            "needs multiple files, prefer `orchestrate/context.py`, "
            "`orchestrate/platform_auth.py`, etc., and re-export stable names from "
            "the package boundary instead of making callers import nested internals."
        )
        return RuleFinding(
            rule_id=self.rule_id,
            title=self.title,
            severity=Severity.HIGH,
            decision=decision_for_context(ctx),
            message=message,
            additional_context=additional_context,
            metadata={
                METADATA_PATH: finding.path_value,
                METADATA_TARGET: finding.target,
                "kind": finding.kind,
                METADATA_LINE: finding.line,
            },
        )

    def _path_finding(
        self,
        ctx: HookContext,
        path_value: str,
    ) -> RuleFinding | None:
        patch_blob = flat_sibling_patch_blob(ctx)
        added_paths, removed_paths = flat_sibling_patch_added_and_removed_paths(
            patch_blob
        )
        if path_value in removed_paths:
            return None
        existing_pre_edit = ctx.event_name in (PRE_TOOL_USE, PERMISSION_REQUEST) and (
            flat_sibling_resolve_candidate_path(ctx, path_value).exists()
        )
        patch_updates_path = f"*** Update File: {path_value}" in patch_blob
        if path_value not in added_paths and (existing_pre_edit or patch_updates_path):
            return None
        module_path = module_path_from_python_file(path_value)
        if len(private_module_segments(module_path)) < 2:
            return None
        return self.finding(
            ctx,
            PrivateImportFinding(
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
            added_source = patch_added_source(source)
            module = parse_module(
                added_source or "",
                ctx.config.python_ast_max_parse_chars,
            )
        if module is None:
            return []
        findings: list[RuleFinding] = []
        for node in ast.walk(module):
            for line, module_name in imported_modules(node):
                if len(private_module_segments(module_name)) < 2:
                    continue
                findings.append(
                    self.finding(
                        ctx,
                        PrivateImportFinding(
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
