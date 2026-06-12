"""Default value builders for lint quality config."""

from __future__ import annotations

from pathlib import Path

from slopgate.policy_defaults import (
    LINT_DEPRECATED_PATTERNS_DEFAULTS,
    LINT_EXCEPTION_SAFETY_DEFAULTS,
    LINT_LOGGING_DEFAULTS,
    LINT_MAGIC_DEFAULTS,
    LINT_PATH_DEFAULTS,
    LINT_SCOPE_DEFAULTS,
    LINT_TESTING_DEFAULTS,
    LINT_THRESHOLD_DEFAULTS,
    LINT_TYPE_SAFETY_DEFAULTS,
    LINT_WRAPPERS_DEFAULTS,
)


def _deprecated_patterns() -> list[tuple[str, str]]:
    patterns: list[tuple[str, str]] = []
    for item in LINT_DEPRECATED_PATTERNS_DEFAULTS["patterns"]:
        if isinstance(item, tuple) and len(item) == 2:
            patterns.append((item[0], item[1]))
            continue
        text = str(item)
        patterns.append((text, text))
    return patterns


def _path_values(root: Path) -> dict[str, object]:
    src_root = root / LINT_PATH_DEFAULTS["src"]
    tests_root = root / LINT_PATH_DEFAULTS["tests"]
    return {
        "project_root": root,
        "src_roots": (src_root,),
        "test_roots": (tests_root,),
        "src_root": src_root,
        "tests_root": tests_root,
        "baseline_path": None,
        "exclude_dirs": {item for item in LINT_PATH_DEFAULTS["exclude_dirs"]},
        "exclude_patterns": [item for item in LINT_PATH_DEFAULTS["exclude_patterns"]],
        "default_scope": LINT_SCOPE_DEFAULTS["default"],
    }


def _threshold_values() -> dict[str, object]:
    return {
        "max_complexity": LINT_THRESHOLD_DEFAULTS["max_complexity"],
        "max_params": LINT_THRESHOLD_DEFAULTS["max_params"],
        "max_method_lines": LINT_THRESHOLD_DEFAULTS["max_method_lines"],
        "max_test_lines": LINT_THRESHOLD_DEFAULTS["max_test_lines"],
        "max_module_lines_soft": LINT_THRESHOLD_DEFAULTS["max_module_lines_soft"],
        "max_module_lines_hard": LINT_THRESHOLD_DEFAULTS["max_module_lines_hard"],
        "max_nesting_depth": LINT_THRESHOLD_DEFAULTS["max_nesting_depth"],
        "max_god_class_methods": LINT_THRESHOLD_DEFAULTS["max_god_class_methods"],
        "max_god_class_lines": LINT_THRESHOLD_DEFAULTS["max_god_class_lines"],
        "max_eager_test_calls": LINT_THRESHOLD_DEFAULTS["max_eager_test_calls"],
        "max_repeated_magic_numbers": LINT_THRESHOLD_DEFAULTS[
            "max_repeated_magic_numbers"
        ],
        "max_repeated_string_literals": LINT_THRESHOLD_DEFAULTS[
            "max_repeated_string_literals"
        ],
        "max_scattered_helpers": LINT_THRESHOLD_DEFAULTS["max_scattered_helpers"],
        "max_duplicate_helper_signatures": LINT_THRESHOLD_DEFAULTS[
            "max_duplicate_helper_signatures"
        ],
        "max_repeated_code_patterns": LINT_THRESHOLD_DEFAULTS[
            "max_repeated_code_patterns"
        ],
        "min_function_body_lines": LINT_THRESHOLD_DEFAULTS["min_function_body_lines"],
        "min_call_sequence_length": LINT_THRESHOLD_DEFAULTS["min_call_sequence_length"],
        "max_line_length": LINT_THRESHOLD_DEFAULTS["max_line_length"],
        "feature_envy_threshold": float(
            LINT_THRESHOLD_DEFAULTS["feature_envy_threshold"]
        ),
        "feature_envy_min_accesses": LINT_THRESHOLD_DEFAULTS[
            "feature_envy_min_accesses"
        ],
    }


def _allowlist_values() -> dict[str, object]:
    return {
        "allowed_numbers": {item for item in LINT_MAGIC_DEFAULTS["allowed_numbers"]},
        "allowed_strings": {item for item in LINT_MAGIC_DEFAULTS["allowed_strings"]},
        "allowed_wrappers": {str(item) for item in LINT_WRAPPERS_DEFAULTS["allowed"]},
    }


def _logging_values() -> dict[str, object]:
    return {
        "logger_function": LINT_LOGGING_DEFAULTS["logger_function"],
        "logger_variable": LINT_LOGGING_DEFAULTS["logger_variable"],
        "logging_infrastructure_path": LINT_LOGGING_DEFAULTS["infrastructure_path"],
        "disallowed_logger_names": {
            item for item in LINT_LOGGING_DEFAULTS["disallowed_names"]
        },
    }


def _type_safety_values() -> dict[str, object]:
    return {
        "ban_any": LINT_TYPE_SAFETY_DEFAULTS["ban_any"],
        "ban_type_suppressions": LINT_TYPE_SAFETY_DEFAULTS["ban_type_suppressions"],
        "suppression_patterns": tuple(
            item for item in LINT_TYPE_SAFETY_DEFAULTS["suppression_patterns"]
        ),
    }


def _exception_values() -> dict[str, object]:
    return {
        "ban_broad_except_swallow": LINT_EXCEPTION_SAFETY_DEFAULTS[
            "ban_broad_except_swallow"
        ],
        "ban_silent_except": LINT_EXCEPTION_SAFETY_DEFAULTS["ban_silent_except"],
        "ban_silent_fallback": LINT_EXCEPTION_SAFETY_DEFAULTS["ban_silent_fallback"],
    }


def _testing_bool_values() -> dict[str, object]:
    return {
        "ban_conditional_assertions": LINT_TESTING_DEFAULTS[
            "ban_conditional_assertions"
        ],
        "ban_fixtures_outside_conftest": LINT_TESTING_DEFAULTS[
            "ban_fixtures_outside_conftest"
        ],
    }


def _test_values() -> dict[str, object]:
    values: dict[str, object] = {
        "max_consecutive_bare_asserts": LINT_TESTING_DEFAULTS[
            "max_consecutive_bare_asserts"
        ],
    }
    values.update(_testing_bool_values())
    return values


def build_default_values(root: Path) -> dict[str, object]:
    values: dict[str, object] = {}
    values.update(_path_values(root))
    values.update(_threshold_values())
    values.update(_allowlist_values())
    values.update(_logging_values())
    values.update(_type_safety_values())
    values.update(_exception_values())
    values.update(_test_values())
    values["deprecated_patterns"] = _deprecated_patterns()
    values["enable_git_base_debt"] = LINT_SCOPE_DEFAULTS["git_base_debt"]
    return values
