"""Lint quality configuration (compatibility module)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict, cast

from slopgate.lint._toml_overrides import apply_paths_overrides, resolve_baseline_path
from slopgate.lint.config_values import build_default_values


@dataclass(frozen=True)
class QualityConfig:
    """Resolved lint quality configuration."""

    project_root: Path
    src_roots: tuple[Path, ...]
    test_roots: tuple[Path, ...]
    src_root: Path
    tests_root: Path
    baseline_path: Path | None

    exclude_dirs: set[str]
    exclude_patterns: list[str]
    default_scope: str

    max_complexity: int
    max_params: int
    max_method_lines: int
    max_test_lines: int
    max_module_lines_soft: int
    max_module_lines_hard: int
    max_nesting_depth: int
    max_god_class_methods: int
    max_god_class_lines: int
    max_eager_test_calls: int
    max_repeated_magic_numbers: int
    max_repeated_string_literals: int
    max_scattered_helpers: int
    max_duplicate_helper_signatures: int
    max_repeated_code_patterns: int
    min_function_body_lines: int
    min_call_sequence_length: int
    max_line_length: int
    feature_envy_threshold: float
    feature_envy_min_accesses: int

    allowed_numbers: set[int]
    allowed_strings: set[str]
    allowed_wrappers: set[str]

    logger_function: str
    logger_variable: str
    logging_infrastructure_path: str
    disallowed_logger_names: set[str]

    ban_any: bool
    ban_type_suppressions: bool
    suppression_patterns: tuple[str, ...]

    ban_broad_except_swallow: bool
    ban_silent_except: bool
    ban_silent_fallback: bool

    max_consecutive_bare_asserts: int
    ban_conditional_assertions: bool
    ban_fixtures_outside_conftest: bool

    deprecated_patterns: list[tuple[str, str]]


_config_instance: QualityConfig | None = None


class _QualityConfigValues(TypedDict):
    project_root: Path
    src_roots: tuple[Path, ...]
    test_roots: tuple[Path, ...]
    src_root: Path
    tests_root: Path
    baseline_path: Path | None
    exclude_dirs: set[str]
    exclude_patterns: list[str]
    default_scope: str
    max_complexity: int
    max_params: int
    max_method_lines: int
    max_test_lines: int
    max_module_lines_soft: int
    max_module_lines_hard: int
    max_nesting_depth: int
    max_god_class_methods: int
    max_god_class_lines: int
    max_eager_test_calls: int
    max_repeated_magic_numbers: int
    max_repeated_string_literals: int
    max_scattered_helpers: int
    max_duplicate_helper_signatures: int
    max_repeated_code_patterns: int
    min_function_body_lines: int
    min_call_sequence_length: int
    max_line_length: int
    feature_envy_threshold: float
    feature_envy_min_accesses: int
    allowed_numbers: set[int]
    allowed_strings: set[str]
    allowed_wrappers: set[str]
    logger_function: str
    logger_variable: str
    logging_infrastructure_path: str
    disallowed_logger_names: set[str]
    ban_any: bool
    ban_type_suppressions: bool
    suppression_patterns: tuple[str, ...]
    ban_broad_except_swallow: bool
    ban_silent_except: bool
    ban_silent_fallback: bool
    max_consecutive_bare_asserts: int
    ban_conditional_assertions: bool
    ban_fixtures_outside_conftest: bool
    deprecated_patterns: list[tuple[str, str]]


def load_config(project_root: Path) -> QualityConfig:
    """Load lint config from repository defaults and ``slopgate.toml`` overrides."""

    root = project_root.resolve()
    values = build_default_values(root)
    apply_paths_overrides(values, root)
    configured_baseline = resolve_baseline_path(root)
    if configured_baseline is not None:
        values["baseline_path"] = configured_baseline
    typed_values = cast(_QualityConfigValues, cast(object, values))
    loaded = QualityConfig(**typed_values)
    set_config(loaded)
    return loaded


def get_config() -> QualityConfig:
    """Return global lint config, loading cwd defaults if needed."""

    global _config_instance
    if _config_instance is None:
        return load_config(Path.cwd())
    return _config_instance


def set_config(config: QualityConfig) -> None:
    """Set global lint config instance."""

    global _config_instance
    _config_instance = config


def reset_config() -> None:
    """Clear global lint config singleton."""

    global _config_instance
    _config_instance = None
