from __future__ import annotations

import re
from dataclasses import dataclass

from slopgate.models import RegexRuleConfig
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
