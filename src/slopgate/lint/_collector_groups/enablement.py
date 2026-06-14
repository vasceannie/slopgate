"""Collector enablement filtering."""

from __future__ import annotations

from slopgate.lint._collector_groups.constants import OPT_IN_CLI_COLLECTORS
from slopgate.lint._collector_groups.types import CollectorResults


def collector_enabled(rule_name: str, enabled_cli_rules: dict[str, bool]) -> bool:
    if rule_name in OPT_IN_CLI_COLLECTORS:
        return enabled_cli_rules.get(rule_name, False)
    if not enabled_cli_rules:
        return True
    return enabled_cli_rules.get(rule_name, True)


def enabled_collectors(collectors: CollectorResults) -> CollectorResults:
    from slopgate.lint._config import get_config

    enabled_cli_rules = get_config().enabled_cli_rules
    return [
        (rule_name, violations)
        for rule_name, violations in collectors
        if collector_enabled(rule_name, enabled_cli_rules)
    ]


__all__ = ["enabled_collectors"]
