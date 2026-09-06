from __future__ import annotations

import re
from dataclasses import dataclass

from slopgate.constants import METADATA_CONTENT, METADATA_PATH, METADATA_TARGET
from slopgate.models import RegexRuleConfig, RuleFinding, Severity
from slopgate.rules.base import Rule
from slopgate.util.metadata_paths import quality_metadata_path
from slopgate.util.payloads import any_path_matches


def compile_regex_patterns(config: RegexRuleConfig) -> list[re.Pattern[str]]:
    """Compile regex rule patterns using the runtime rule flags."""
    flags = 0
    if config.multiline:
        flags |= re.MULTILINE | re.DOTALL
    if not config.case_sensitive:
        flags |= re.IGNORECASE
    return [re.compile(pattern, flags) for pattern in config.patterns]


@dataclass(slots=True)
class RegexHit:
    path: str | None
    snippet: str | None = None
    category: str | None = None


@dataclass(slots=True)
class RegexRuleMatcher:
    """Pattern and path matching helpers for :class:`RegexRule`."""

    config: RegexRuleConfig
    patterns: list[re.Pattern[str]]

    def tool_matches(self, tool_name: str) -> bool:
        if not self.config.tool_matchers:
            return True
        return any(
            re.fullmatch(pattern, tool_name) for pattern in self.config.tool_matchers
        )

    def path_allowed(self, path_value: str | None) -> bool:
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

    def matches_text(self, value: str) -> bool:
        return self.first_match_index(value) is not None

    def first_match_index(self, value: str) -> int | None:
        for index, pattern in enumerate(self.patterns):
            if pattern.search(value):
                return index
        return None

    def category_at(self, index: int | None) -> str | None:
        categories = self.config.pattern_categories
        if index is None or not categories or index >= len(categories):
            return None
        return categories[index]

    def path_hit(self, path_value: str, text: str) -> RegexHit | None:
        match_index = self.first_match_index(text)
        if not self.path_allowed(path_value) or match_index is None:
            return None
        return RegexHit(path=path_value, category=self.category_at(match_index))

    def scalar_hit(self, value: str) -> list[RegexHit]:
        if not value:
            return []
        match_index = self.first_match_index(value)
        if match_index is None:
            return []
        return [RegexHit(path=None, category=self.category_at(match_index))]


class RegexConfiguredRule(Rule):
    """Base for rules driven by a :class:`RegexRuleConfig` identity."""

    config: RegexRuleConfig

    def __init__(self, config: RegexRuleConfig, enabled: bool = True) -> None:
        super().__init__(enabled=enabled)
        self.config = config
        self.rule_id = config.rule_id
        self.title = config.title
        self.events = tuple(config.events)


def render_regex_message(
    config: RegexRuleConfig, rule_id: str, hits: list[RegexHit]
) -> str:
    """Render a regex rule message for the first matching hit."""
    category = hits[0].category if hits else None
    if category and config.category_messages:
        category_message = config.category_messages.get(category)
        if category_message:
            return category_message
    if not config.message:
        return rule_id
    first_path = hits[0].path or ""
    all_paths = ", ".join(sorted({hit.path for hit in hits if hit.path}))
    return config.message.format(
        path=first_path, matched_paths=all_paths, rule_id=rule_id
    )


def build_regex_finding(
    config: RegexRuleConfig, rule_id: str, title: str, hits: list[RegexHit]
) -> RuleFinding:
    """Build a regex rule finding from the collected hits."""
    is_context = config.action == "context"
    hit_paths = [hit.path for hit in hits if hit.path]
    primary_category = hits[0].category if hits else None
    metadata: dict[str, object] = {METADATA_TARGET: config.target, "hits": hit_paths}
    if primary_category:
        metadata["category"] = primary_category
    if hit_paths and config.target in {METADATA_CONTENT, METADATA_PATH}:
        for hit_path in hit_paths:
            display_path = quality_metadata_path(hit_path)
            if display_path:
                metadata[METADATA_PATH] = display_path
                break
    return RuleFinding(
        rule_id=rule_id,
        title=title,
        severity=Severity.from_value(config.severity),
        decision=None if is_context else config.action,
        message=None if is_context else render_regex_message(config, rule_id, hits),
        additional_context=config.additional_context,
        metadata=metadata,
    )
