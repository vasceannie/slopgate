from __future__ import annotations
from typing import TYPE_CHECKING, final

from typing_extensions import override

from slopgate.constants import (
    METADATA_PATH,
)
from slopgate.models import RegexRuleConfig, RuleFinding, Severity
from slopgate.rules.base import Rule
from slopgate.rules.regex_rule_matching import (
    RegexHit,
    RegexRuleMatcher,
    compile_regex_patterns,
)
from slopgate.util.metadata_paths import quality_metadata_path
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
class RegexRule(Rule):
    config: RegexRuleConfig
    _matcher: RegexRuleMatcher

    def __init__(self, config: RegexRuleConfig, enabled: bool = True) -> None:
        super().__init__(enabled=enabled)
        self.config = config
        self.rule_id = config.rule_id
        self.title = config.title
        self.events = tuple(config.events)
        self._matcher = RegexRuleMatcher(
            config=config,
            patterns=compile_regex_patterns(config),
        )

    def _render_message(self, hits: list[RegexHit]) -> str:
        if not self.config.message:
            return self.rule_id
        first_path = hits[0].path or ""
        all_paths = ", ".join(sorted({hit.path for hit in hits if hit.path}))
        return self.config.message.format(
            path=first_path, matched_paths=all_paths, rule_id=self.rule_id
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

    def _build_finding(self, hits: list[RegexHit]) -> RuleFinding:
        is_context = self.config.action == "context"
        hit_paths = [hit.path for hit in hits if hit.path]
        metadata: dict[str, object] = {
            "target": self.config.target,
            "hits": hit_paths,
        }
        if hit_paths and self.config.target in {"content", METADATA_PATH}:
            for hit_path in hit_paths:
                display_path = quality_metadata_path(hit_path)
                if display_path:
                    metadata[METADATA_PATH] = display_path
                    break
        return RuleFinding(
            rule_id=self.rule_id,
            title=self.title,
            severity=Severity.from_value(self.config.severity),
            decision=None if is_context else self.config.action,
            message=None if is_context else self._render_message(hits),
            additional_context=self.config.additional_context,
            metadata=metadata,
        )

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
        return [self._build_finding(hits)]
