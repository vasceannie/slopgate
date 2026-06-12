from __future__ import annotations

from dataclasses import dataclass, replace

from slopgate.models import RuntimeConfig


@dataclass(frozen=True, slots=True)
class GuardRuleConfigOverrides:
    search_reminder_message: str | None = None
    post_edit_quality_enabled: bool | None = None
    post_edit_quality_block_on_failure: bool | None = None
    post_edit_quality_commands: dict[str, list[str]] | None = None
    system_path_prefixes: list[str] | None = None


@dataclass(frozen=True, slots=True)
class AstRuleConfigOverrides:
    python_max_complexity: int | None = None
    python_long_method_lines: int | None = None
    python_long_parameter_limit: int | None = None
    python_max_nesting_depth: int | None = None
    python_max_line_length: int | None = None
    python_feature_envy_min_accesses: int | None = None
    python_max_god_class_methods: int | None = None
    python_import_fanout_limit: int | None = None


def apply_guard_rule_config_overrides(
    config: RuntimeConfig,
    overrides: GuardRuleConfigOverrides,
) -> RuntimeConfig:
    if overrides.search_reminder_message is not None:
        config = replace(
            config, search_reminder_message=overrides.search_reminder_message
        )
    if overrides.post_edit_quality_enabled is not None:
        config = replace(
            config, post_edit_quality_enabled=overrides.post_edit_quality_enabled
        )
    if overrides.post_edit_quality_block_on_failure is not None:
        config = replace(
            config,
            post_edit_quality_block_on_failure=(
                overrides.post_edit_quality_block_on_failure
            ),
        )
    if overrides.post_edit_quality_commands is not None:
        config = replace(
            config, post_edit_quality_commands=overrides.post_edit_quality_commands
        )
    if overrides.system_path_prefixes is not None:
        config = replace(config, system_path_prefixes=overrides.system_path_prefixes)
    return config


def apply_ast_rule_config_overrides(
    config: RuntimeConfig,
    overrides: AstRuleConfigOverrides,
) -> RuntimeConfig:
    if overrides.python_max_complexity is not None:
        config = replace(config, python_max_complexity=overrides.python_max_complexity)
    if overrides.python_long_method_lines is not None:
        config = replace(
            config, python_long_method_lines=overrides.python_long_method_lines
        )
    if overrides.python_long_parameter_limit is not None:
        config = replace(
            config, python_long_parameter_limit=overrides.python_long_parameter_limit
        )
    if overrides.python_max_nesting_depth is not None:
        config = replace(
            config, python_max_nesting_depth=overrides.python_max_nesting_depth
        )
    if overrides.python_max_line_length is not None:
        config = replace(
            config, python_max_line_length=overrides.python_max_line_length
        )
    if overrides.python_feature_envy_min_accesses is not None:
        config = replace(
            config,
            python_feature_envy_min_accesses=(
                overrides.python_feature_envy_min_accesses
            ),
        )
    if overrides.python_max_god_class_methods is not None:
        config = replace(
            config,
            python_max_god_class_methods=overrides.python_max_god_class_methods,
        )
    if overrides.python_import_fanout_limit is not None:
        config = replace(
            config, python_import_fanout_limit=overrides.python_import_fanout_limit
        )
    return config
