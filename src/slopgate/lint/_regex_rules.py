"""Lint collectors backed by declarative regex rules."""

from __future__ import annotations

from slopgate.config import load_config as load_runtime_config
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


def _matcher_for_rule(config: RegexRuleConfig) -> RegexRuleMatcher:
    return RegexRuleMatcher(config=config, patterns=compile_regex_patterns(config))


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


def _content_violation(
    config: RegexRuleConfig,
    matcher: RegexRuleMatcher,
    parsed_file: ParsedFile,
) -> Violation | None:
    content = "\n".join(parsed_file.lines)
    hit = matcher.path_hit(parsed_file.rel, content)
    if hit is None:
        return None
    return _regex_violation(config, parsed_file.rel)


def _path_violation(
    config: RegexRuleConfig,
    matcher: RegexRuleMatcher,
    parsed_file: ParsedFile,
) -> Violation | None:
    hit = matcher.path_hit(parsed_file.rel, parsed_file.rel)
    if hit is None:
        return None
    return _regex_violation(config, parsed_file.rel)


def _regex_violation(config: RegexRuleConfig, relative_path: str) -> Violation:
    return Violation(
        rule=config.rule_id,
        relative_path=relative_path,
        identifier=f"regex:{config.target}",
        detail=_render_detail(config, relative_path),
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


def _violations_for_rule(
    config: RegexRuleConfig,
    parsed_files: list[ParsedFile],
) -> list[Violation]:
    matcher = _matcher_for_rule(config)
    detector = _content_violation if config.target == "content" else _path_violation
    return [
        violation
        for parsed_file in parsed_files
        if (violation := detector(config, matcher, parsed_file)) is not None
    ]


def regex_rule_collectors(
    parsed_src: list[ParsedFile],
    parsed_tests: list[ParsedFile],
) -> list[tuple[str, list[Violation]]]:
    """Return enabled CLI lint collectors produced from regex rule config."""
    quality_config = get_config()
    runtime_config = load_runtime_config(
        quality_config.project_root,
        quality_config.project_root,
        ensure_enrollment=False,
        ensure_trace=False,
    )
    parsed_files = [*parsed_src, *parsed_tests]
    return [
        (config.rule_id, _violations_for_rule(config, parsed_files))
        for config in runtime_config.regex_rules
        if _rule_cli_enabled(runtime_config, config)
    ]
