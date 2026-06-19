"""Python runtime policy config helpers."""

from __future__ import annotations

from dataclasses import dataclass

from slopgate.policy_defaults import RUNTIME_POLICY_DEFAULTS

from ._coerce import bool_value, float_value, int_value, object_dict


@dataclass(frozen=True, slots=True)
class PythonRuntimeSettings:
    ast_enabled: bool
    max_parse_chars: int
    long_method_lines: int
    long_parameter_limit: int
    max_complexity: int
    max_nesting_depth: int
    max_god_class_methods: int
    max_line_length: int
    feature_envy_threshold: float
    feature_envy_min_accesses: int
    import_fanout_limit: int


@dataclass(frozen=True, slots=True)
class _PythonAstThresholdKeys:
    threshold: str
    python_ast: str
    default: str


def _runtime_policy_int_threshold(thresholds: dict[str, object], key: str) -> int:
    default = int(RUNTIME_POLICY_DEFAULTS[key])
    return int_value(thresholds.get(key), default)


def _runtime_policy_float_threshold(thresholds: dict[str, object], key: str) -> float:
    default = float(RUNTIME_POLICY_DEFAULTS[key])
    return float_value(thresholds.get(key), default)


def _python_ast_threshold_int(
    thresholds: dict[str, object],
    python_ast: dict[str, object],
    keys: _PythonAstThresholdKeys,
) -> int:
    value = thresholds.get(
        keys.threshold,
        python_ast.get(keys.python_ast, RUNTIME_POLICY_DEFAULTS[keys.default]),
    )
    return int_value(value, int(RUNTIME_POLICY_DEFAULTS[keys.default]))


def python_runtime_settings(
    raw: dict[str, object], thresholds: dict[str, object]
) -> PythonRuntimeSettings:
    python_ast = object_dict(raw.get("python_ast", {}))
    return PythonRuntimeSettings(
        ast_enabled=bool_value(python_ast.get("enabled"), True),
        max_parse_chars=int_value(
            python_ast.get("max_parse_chars"),
            int(RUNTIME_POLICY_DEFAULTS["max_parse_chars"]),
        ),
        long_method_lines=_python_ast_threshold_int(
            thresholds,
            python_ast,
            _PythonAstThresholdKeys(
                "max_method_lines", "long_method_lines", "long_method_lines"
            ),
        ),
        long_parameter_limit=_python_ast_threshold_int(
            thresholds,
            python_ast,
            _PythonAstThresholdKeys(
                "max_params", "long_parameter_limit", "long_parameter_limit"
            ),
        ),
        max_complexity=_runtime_policy_int_threshold(thresholds, "max_complexity"),
        max_nesting_depth=_runtime_policy_int_threshold(
            thresholds, "max_nesting_depth"
        ),
        max_god_class_methods=_runtime_policy_int_threshold(
            thresholds, "max_god_class_methods"
        ),
        max_line_length=_runtime_policy_int_threshold(thresholds, "max_line_length"),
        feature_envy_threshold=_runtime_policy_float_threshold(
            thresholds, "feature_envy_threshold"
        ),
        feature_envy_min_accesses=_runtime_policy_int_threshold(
            thresholds, "feature_envy_min_accesses"
        ),
        import_fanout_limit=_runtime_policy_int_threshold(
            thresholds, "import_fanout_limit"
        ),
    )
