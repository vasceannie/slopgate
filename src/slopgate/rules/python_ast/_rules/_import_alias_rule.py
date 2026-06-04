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

from ._import_helpers import _allowed_import_alias as _allowed_import_alias, _import_alias_full_name as _import_alias_full_name, _import_alias_replacement as _import_alias_replacement, _patch_added_source as _patch_added_source


class PythonImportAliasRule(Rule):
    """PY-IMPORT-002: Block non-standard import aliases.

    Arbitrary ``as`` aliases let agents make duplicated blocks look different
    enough to evade clone/repeated-block detectors. Keep only well-known library
    coupling aliases such as ``pandas as pd`` or ``polars as pl``.
    """

    rule_id = "PY-IMPORT-002"
    title = "Block non-standard Python import aliases"
    events = (PRE_TOOL_USE, PERMISSION_REQUEST, POST_TOOL_USE)

    @staticmethod
    def _iter_modules(source: str, max_chars: int) -> list[ast.Module]:
        modules: list[ast.Module] = []
        module = parse_module(source, max_chars)
        if module is not None:
            modules.append(module)
            return modules
        added_source = _patch_added_source(source)
        if added_source is None:
            return modules
        added_module = parse_module(added_source, max_chars)
        if added_module is not None:
            modules.append(added_module)
        return modules

    @staticmethod
    def _collect_aliases(module: ast.Module) -> list[tuple[int, str, str, str, str]]:
        aliases: list[tuple[int, str, str, str, str]] = []
        for node in ast.walk(module):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            for name in node.names:
                if name.asname is None or _allowed_import_alias(node, name):
                    continue
                replacement, usage = _import_alias_replacement(node, name)
                aliases.append((
                    node.lineno,
                    _import_alias_full_name(node, name),
                    name.asname,
                    replacement,
                    usage,
                ))
        return aliases

    def _check_source(
        self,
        source: str,
        path_value: str,
        ctx: HookContext,
    ) -> list[RuleFinding]:
        findings: list[RuleFinding] = []
        max_chars = ctx.config.python_ast_max_parse_chars
        for module in self._iter_modules(source, max_chars):
            for lineno, imported_name, asname, replacement, usage in self._collect_aliases(module):
                message = (
                    f"`{path_value}` imports `{imported_name} as {asname}` on line "
                    f"{lineno}. Non-standard import aliases are blocked because "
                    "they hide duplicated code from clone/repeated-block detectors. "
                    "Use the real module/name or extract shared behavior instead. "
                    "Only canonical library aliases are allowed, e.g. `pandas as pd`, "
                    "`polars as pl`, `numpy as np`, or `matplotlib.pyplot as plt`.\n\n"
                    "Use this instead:\n"
                    f"    {replacement}\n"
                    f"Then call: `{usage}`"
                )
                findings.append(
                    RuleFinding(
                        rule_id=self.rule_id,
                        title=self.title,
                        severity=Severity.HIGH,
                        decision=decision_for_context(ctx),
                        message=message,
                        additional_context=(
                            "Remove the alias or refactor the duplicated block; do "
                            "not rename imports to make duplicate code look unique."
                        ),
                        metadata={
                            METADATA_PATH: path_value,
                            "line": lineno,
                            "imported_name": imported_name,
                            "alias": asname,
                        },
                    )
                )
        return findings

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not is_rule_enabled(ctx, self.rule_id):
            return []
        return evaluate_common(self, ctx, self._check_source)
