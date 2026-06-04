from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from typing_extensions import override

from vibeforcer.constants import (
    METADATA_PATH,
)
from vibeforcer.models import RegexRuleConfig, RuleFinding, Severity
from vibeforcer.rules.base import Rule
from vibeforcer.util.payloads import any_path_matches

if TYPE_CHECKING:
    from vibeforcer.context import HookContext


@dataclass(slots=True)
class RegexHit:
    path: str | None
    snippet: str | None = None


def _collect_content_hits(rule: RegexRule, ctx: HookContext) -> list[RegexHit]:
    hits: list[RegexHit] = []
    for content_target in ctx.content_targets:
        hit = rule._path_hit(content_target.path, content_target.content)
        if hit is not None:
            hits.append(hit)
    return hits


def _collect_command_hits(rule: RegexRule, ctx: HookContext) -> list[RegexHit]:
    return rule._scalar_hit(ctx.shell_command)


def _collect_path_hits(rule: RegexRule, ctx: HookContext) -> list[RegexHit]:
    hits: list[RegexHit] = []
    for path_value in ctx.candidate_paths:
        hit = rule._path_hit(path_value, path_value)
        if hit is not None:
            hits.append(hit)
    return hits


def _collect_prompt_hits(rule: RegexRule, ctx: HookContext) -> list[RegexHit]:
    return rule._scalar_hit(ctx.user_prompt)


@final
class RegexRule(Rule):
    config: RegexRuleConfig
    _patterns: list[re.Pattern[str]]

    def __init__(self, config: RegexRuleConfig, enabled: bool = True) -> None:
        super().__init__(enabled=enabled)
        self.config = config
        self.rule_id = config.rule_id
        self.title = config.title
        self.events = tuple(config.events)
        flags = 0
        if config.multiline:
            flags |= re.MULTILINE | re.DOTALL
        if not config.case_sensitive:
            flags |= re.IGNORECASE
        self._patterns = [re.compile(pattern, flags) for pattern in config.patterns]

    def _tool_matches(self, tool_name: str) -> bool:
        if not self.config.tool_matchers:
            return True
        return any(
            re.fullmatch(pattern, tool_name) for pattern in self.config.tool_matchers
        )

    def _path_allowed(self, path_value: str | None) -> bool:
        if not path_value:
            return True
        if self.config.path_globs and not any_path_matches(
            path_value, self.config.path_globs
        ):
            return False
        if self.config.exclude_path_globs and any_path_matches(
            path_value, self.config.exclude_path_globs
        ):
            return False
        return True

    def _render_message(self, hits: list[RegexHit]) -> str:
        if not self.config.message:
            return self.rule_id
        first_path = hits[0].path or ""
        all_paths = ", ".join(sorted({hit.path for hit in hits if hit.path}))
        return self.config.message.format(
            path=first_path, matched_paths=all_paths, rule_id=self.rule_id
        )

    def _matches_text(self, value: str) -> bool:
        return any(pattern.search(value) for pattern in self._patterns)

    def _path_hit(self, path_value: str, text: str) -> RegexHit | None:
        if not self._path_allowed(path_value):
            return None
        if not self._matches_text(text):
            return None
        return RegexHit(path=path_value)

    def _scalar_hit(self, value: str) -> list[RegexHit]:
        return [RegexHit(path=None)] if value and self._matches_text(value) else []

    def _build_finding(self, hits: list[RegexHit]) -> RuleFinding:
        is_context = self.config.action == "context"
        return RuleFinding(
            rule_id=self.rule_id,
            title=self.title,
            severity=Severity.from_value(self.config.severity),
            decision=None if is_context else self.config.action,
            message=None if is_context else self._render_message(hits),
            additional_context=self.config.additional_context,
            metadata={
                "target": self.config.target,
                "hits": [hit.path for hit in hits if hit.path],
            },
        )

    @override
    def evaluate(self, ctx: "HookContext") -> list[RuleFinding]:
        if not self.enabled or not self.supports(ctx.event_name):
            return []
        if not self._tool_matches(ctx.tool_name):
            return []

        collectors = {
            "content": _collect_content_hits,
            "command": _collect_command_hits,
            METADATA_PATH: _collect_path_hits,
            "prompt": _collect_prompt_hits,
        }
        collector = collectors.get(self.config.target)
        if collector is None:
            return []
        hits = collector(self, ctx)
        if not hits:
            return []
        return [self._build_finding(hits)]
