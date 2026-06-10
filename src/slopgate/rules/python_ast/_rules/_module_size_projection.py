"""Python AST runtime rule for oversized module projection checks."""

from __future__ import annotations
from typing import TYPE_CHECKING, NamedTuple, final
from typing_extensions import override
from slopgate.constants import (
    LINT_MAX_MODULE_LINES_HARD,
    LINT_MAX_MODULE_LINES_SOFT,
    METADATA_PATH,
)
from slopgate.models import RuleFinding, Severity
from slopgate.rules.base import Rule
from .._helpers import decision_for_context
from ._module_size_guidance import (
    module_split_scenario,
    oversized_module_split_guidance,
)
from ._module_size_sources import (
    is_line_count_camouflage,
    pre_python_camouflage_sources,
    python_structural_sources,
)
from ._source_parse import line_count, python_ast_rule_is_disabled

if TYPE_CHECKING:
    from slopgate.context import HookContext


class _LineCountCamouflageFinding(NamedTuple):
    path_value: str
    before_lines: int
    after_lines: int


class ModuleSizeFinding(NamedTuple):
    path_value: str
    line_count: int
    hard: bool


class _SplitContext(NamedTuple):
    scenario: str
    decision: str
    guidance: str


def _split_context(ctx: HookContext, path_value: str) -> _SplitContext:
    scenario = module_split_scenario(path_value)
    return _SplitContext(
        scenario,
        decision_for_context(ctx),
        oversized_module_split_guidance(path_value, scenario),
    )


@final
class PythonModuleSizeRule(Rule):
    """Block Python modules that exceed lint module line-count thresholds."""

    rule_id = "PY-CODE-018"
    title = "Block oversized Python module"
    events = ("PreToolUse", "PermissionRequest")

    def finding(self, ctx: HookContext, finding: ModuleSizeFinding) -> RuleFinding:
        threshold = (
            LINT_MAX_MODULE_LINES_HARD if finding.hard else LINT_MAX_MODULE_LINES_SOFT
        )
        collector = "oversized-module" if finding.hard else "oversized-module-soft"
        severity = Severity.HIGH if finding.hard else Severity.MEDIUM
        split = _split_context(ctx, finding.path_value)
        return RuleFinding(
            rule_id=self.rule_id,
            title=self.title,
            severity=severity,
            decision=split.decision,
            message=f"Python module `{finding.path_value}` is {collector}: {finding.line_count} lines exceeds limit {threshold}. Use the {split.scenario} split plan before writing it; line-count camouflage will be blocked.",
            additional_context=split.guidance,
            metadata={
                METADATA_PATH: finding.path_value,
                "collector": collector,
                "split_scenario": split.scenario,
                "lines": finding.line_count,
                "limit": threshold,
            },
        )

    def _camouflage_finding(
        self, ctx: HookContext, finding: _LineCountCamouflageFinding
    ) -> RuleFinding:
        split = _split_context(ctx, finding.path_value)
        removed = finding.before_lines - finding.after_lines
        return RuleFinding(
            rule_id=self.rule_id,
            title="Block oversized-module line-count camouflage",
            severity=Severity.HIGH,
            decision=split.decision,
            message=f"Line-count camouflage on oversized module `{finding.path_value}`: the edit removes {removed} blank/spacing lines ({finding.before_lines} -> {finding.after_lines}) while keeping the same nonblank content. Do a package/facade split instead of shaving empty space.",
            additional_context=split.guidance,
            metadata={
                METADATA_PATH: finding.path_value,
                "collector": "line-count-camouflage",
                "split_scenario": split.scenario,
                "before_lines": finding.before_lines,
                "after_lines": finding.after_lines,
                "removed_lines": removed,
            },
        )

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if python_ast_rule_is_disabled(ctx, self.rule_id):
            return []
        findings: list[RuleFinding] = []
        camouflage_paths: set[str] = set()
        for path_value, before, after in pre_python_camouflage_sources(ctx):
            if not is_line_count_camouflage(before, after):
                continue
            camouflage_paths.add(path_value)
            findings.append(
                self._camouflage_finding(
                    ctx,
                    _LineCountCamouflageFinding(
                        path_value, line_count(before), line_count(after)
                    ),
                )
            )
        for path_value, source in python_structural_sources(ctx):
            if path_value in camouflage_paths:
                continue
            count = line_count(source)
            if count > LINT_MAX_MODULE_LINES_HARD:
                findings.append(
                    self.finding(ctx, ModuleSizeFinding(path_value, count, hard=True))
                )
            elif count > LINT_MAX_MODULE_LINES_SOFT:
                findings.append(
                    self.finding(ctx, ModuleSizeFinding(path_value, count, hard=False))
                )
        return findings
