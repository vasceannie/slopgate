"""Lint collectors backed by declarative regex rules."""

from __future__ import annotations

from pathlib import Path

from slopgate.config import load_config
from slopgate.constants import METADATA_PATH
from slopgate.lint._baseline import Violation
from slopgate.lint._config import get_config
from slopgate.lint._helpers import ParsedFile
from slopgate.models import RegexRuleConfig, RuntimeConfig
from slopgate.rules.regex_rule_matching import (
    RegexRuleMatcher,
    compile_regex_patterns,
)

CLI_REGEX_TARGETS = frozenset(("content", METADATA_PATH))


def _render_detail(config: RegexRuleConfig, matched_path: str) -> str:
    if not config.message:
        return config.title
    try:
        return config.message.format(
            path=matched_path,
            matched_paths=matched_path,
            rule_id=config.rule_id,
        )
    except (IndexError, KeyError, ValueError):
        return config.message


def _rule_violation(
    config: RegexRuleConfig,
    matcher: RegexRuleMatcher,
    parsed_file: ParsedFile,
) -> Violation | None:
    matched_value = (
        "\n".join(parsed_file.lines)
        if config.target == "content"
        else parsed_file.rel
    )
    hit = matcher.path_hit(parsed_file.rel, matched_value)
    if hit is None:
        return None
    return Violation(
        rule=config.rule_id,
        relative_path=parsed_file.rel,
        identifier=f"regex:{config.target}",
        detail=_render_detail(config, parsed_file.rel),
        metadata={
            "source": "regex_rule",
            "title": config.title,
            "target": config.target,
        },
    )


def _rule_cli_enabled(runtime_config: RuntimeConfig, config: RegexRuleConfig) -> bool:
    if config.target not in CLI_REGEX_TARGETS:
        return False
    return runtime_config.rule_surfaces.get(config.rule_id, None) is not None and (
        runtime_config.rule_surfaces[config.rule_id].cli.enabled is True
    )


def cli_regex_rule_configs(
    project_root: Path | None = None,
) -> tuple[RegexRuleConfig, ...]:
    """Return configured regex rules that participate in batch lint."""
    root = project_root or get_config().project_root
    runtime_config = load_config(
        root,
        root,
        ensure_enrollment=False,
        ensure_trace=False,
    )
    return tuple(
        config
        for config in runtime_config.regex_rules
        if _rule_cli_enabled(runtime_config, config)
    )


def _violations_for_rule(
    config: RegexRuleConfig,
    parsed_files: list[ParsedFile],
) -> list[Violation]:
    matcher = RegexRuleMatcher(
        config=config,
        patterns=compile_regex_patterns(config),
    )
    return [
        violation
        for parsed_file in parsed_files
        if (violation := _rule_violation(config, matcher, parsed_file)) is not None
    ]


def regex_rule_collectors(
    parsed_src: list[ParsedFile],
    parsed_tests: list[ParsedFile],
) -> list[tuple[str, list[Violation]]]:
    """Return enabled CLI lint collectors produced from regex rule config."""
    parsed_files = [*parsed_src, *parsed_tests]
    return [
        (config.rule_id, _violations_for_rule(config, parsed_files))
        for config in cli_regex_rule_configs()
    ]
