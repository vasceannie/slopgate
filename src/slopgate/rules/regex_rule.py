from __future__ import annotations
from typing import TYPE_CHECKING, final

from typing_extensions import override

from slopgate.constants import METADATA_PATH
from slopgate.models import RegexRuleConfig, RuleFinding
from slopgate.rules.regex_rule_matching import (
    RegexConfiguredRule,
    RegexHit,
    RegexRuleMatcher,
    build_regex_finding,
    compile_regex_patterns,
)
from slopgate.util.payloads import is_mutating_tool_use

if TYPE_CHECKING:
    from slopgate.context import HookContext

EDIT_ONLY_PATH_RULE_IDS = frozenset(
    {
        "CONFIG-002",
        "CONFIG-004",
        "FE-LINTER-001",
        "PY-LINTER-001",
        "PY-QUALITY-011",
        "QA-PATH-001",
        "QA-PATH-003",
        "WARN-BASELINE-001",
    }
)


@final
class RegexRule(RegexConfiguredRule):
    _matcher: RegexRuleMatcher

    def __init__(self, config: RegexRuleConfig, enabled: bool = True) -> None:
        super().__init__(config=config, enabled=enabled)
        self._matcher = RegexRuleMatcher(
            config=config,
            patterns=compile_regex_patterns(config),
        )

    def _collect_content_hits(self, ctx: HookContext) -> list[RegexHit]:
        hits: list[RegexHit] = []
        for content_target in ctx.content_targets:
            hit = self._matcher.path_hit(content_target.path, content_target.content)
            if hit is not None:
                hits.append(hit)
        return hits

    def _collect_path_hits(self, ctx: HookContext) -> list[RegexHit]:
        if self.rule_id in EDIT_ONLY_PATH_RULE_IDS and not is_mutating_tool_use(ctx):
            return []
        hits: list[RegexHit] = []
        for path_value in ctx.candidate_paths:
            hit = self._matcher.path_hit(path_value, path_value)
            if hit is not None:
                hits.append(hit)
        return hits

    @override
    def evaluate(self, ctx: "HookContext") -> list[RuleFinding]:
        if not self.enabled or not self.supports(ctx.event_name):
            return []
        if not self._matcher.tool_matches(ctx.tool_name):
            return []

        if self.config.target == "content":
            hits = self._collect_content_hits(ctx)
        elif self.config.target == "command":
            hits = self._matcher.scalar_hit(ctx.shell_command)
        elif self.config.target == METADATA_PATH:
            hits = self._collect_path_hits(ctx)
        elif self.config.target == "prompt":
            hits = self._matcher.scalar_hit(ctx.user_prompt)
        else:
            return []
        if not hits:
            return []
        return [build_regex_finding(self.config, self.rule_id, self.title, hits)]
