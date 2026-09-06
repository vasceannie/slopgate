"""Linear-time detection of exception handlers that log and return empty defaults.

PY-QUALITY-005 was previously a nested-quantifier regex whose two lazy handler-body
loops could backtrack exponentially on realistic content and hold the GIL long
enough to freeze the resident hook daemon (incident 2026-09-06). This module
scans handler bodies line by line in linear time and preserves the rule's
observable semantics: a same-handler log call followed by an empty-default return.
"""

from __future__ import annotations

from typing import final

from typing_extensions import override

from slopgate.constants import METADATA_CONTENT
from slopgate.context import HookContext
from slopgate.models import RegexRuleConfig, RuleFinding
from slopgate.rules.regex_rule_matching import (
    RegexConfiguredRule,
    RegexHit,
    RegexRuleMatcher,
    build_regex_finding,
)

DEFAULT_SWALLOW_RULE_ID = "PY-QUALITY-005"

_EXCEPT_PREFIX = "except"
_RETURN_PREFIX = "return"
_EMPTY_DEFAULTS = frozenset({"{}", "[]", "set()", '""', "''", "0", "false"})
_LOGGER_MARKERS = ("logger.", "logging.")


def _is_blank_line(line: str) -> bool:
    return not line.strip(" \t")


def _handler_indent(line: str) -> str | None:
    indent = line[: len(line) - len(line.lstrip(" \t"))]
    body = line[len(indent) :]
    if not body.lower().startswith(_EXCEPT_PREFIX) or ":" not in body:
        return None
    return indent


def _continues_handler(line: str, indent: str) -> bool:
    return (
        line.startswith(indent)
        and len(line) > len(indent)
        and line[len(indent)] in " \t"
    )


def _logs_failure(line: str) -> bool:
    lowered = line.lower()
    return any(marker in lowered for marker in _LOGGER_MARKERS)


def _returns_empty_default(line: str) -> bool:
    stripped = line.strip().lower()
    if not stripped.startswith(_RETURN_PREFIX):
        return False
    remainder = stripped[len(_RETURN_PREFIX) :]
    if not remainder or not remainder[0].isspace():
        return False
    return remainder.strip() in _EMPTY_DEFAULTS


def _handler_returns_empty_after_logging(
    lines: list[str], start: int, indent: str
) -> bool:
    seen_logger = False
    for line in lines[start:]:
        if _is_blank_line(line):
            continue
        if not _continues_handler(line, indent):
            return False
        if not seen_logger and _logs_failure(line):
            seen_logger = True
        elif seen_logger and _returns_empty_default(line):
            return True
    return False


def content_has_logged_empty_default_return(content: str) -> bool:
    """Return True when an except handler logs and then returns an empty default."""
    lines = content.split("\n")
    for index, line in enumerate(lines):
        indent = _handler_indent(line)
        if indent is None:
            continue
        if _handler_returns_empty_after_logging(lines, index + 1, indent):
            return True
    return False


@final
class DefaultSwallowRule(RegexConfiguredRule):
    """Deny exception handlers that log and swallow failures behind empty defaults."""

    _matcher: RegexRuleMatcher

    def __init__(self, config: RegexRuleConfig, enabled: bool = True) -> None:
        super().__init__(config=config, enabled=enabled)
        self._matcher = RegexRuleMatcher(config=config, patterns=[])

    @override
    def evaluate(self, ctx: HookContext) -> list[RuleFinding]:
        if not self.enabled or not self.supports(ctx.event_name):
            return []
        if not self._matcher.tool_matches(ctx.tool_name):
            return []
        if self.config.target != METADATA_CONTENT:
            return []
        hits = [
            RegexHit(path=content_target.path)
            for content_target in ctx.content_targets
            if self._matcher.path_allowed(content_target.path)
            and content_has_logged_empty_default_return(content_target.content)
        ]
        if not hits:
            return []
        return [
            build_regex_finding(
                config=self.config, rule_id=self.rule_id, title=self.title, hits=hits
            )
        ]
