from __future__ import annotations

import re
from dataclasses import dataclass

from slopgate.models import RegexRuleConfig
from slopgate.util.payloads import any_path_matches


@dataclass(slots=True)
class RegexHit:
    path: str | None
    snippet: str | None = None


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
        return any(pattern.search(value) for pattern in self.patterns)

    def path_hit(self, path_value: str, text: str) -> RegexHit | None:
        if not self.path_allowed(path_value):
            return None
        if not self.matches_text(text):
            return None
        return RegexHit(path=path_value)

    def scalar_hit(self, value: str) -> list[RegexHit]:
        return [RegexHit(path=None)] if value and self.matches_text(value) else []
