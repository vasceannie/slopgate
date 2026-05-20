from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from vibeforcer.models import RegexRuleConfig, RuntimeConfig
from vibeforcer.policy_defaults import RUNTIME_POLICY_DEFAULTS

from ._coerce import (
    _bool_value,
    _command_map,
    _float_value,
    _int_value,
    _object_dict,
    _string_list,
    _string_value,
)
from ._io import _load_toml
from ._repo import _DISABLE_SENTINELS

def _resolve_trace_dir(raw: dict[str, object], root: Path) -> Path:
    trace_dir_raw = str(raw.get("trace_dir", "logs"))
    trace_dir_path = Path(trace_dir_raw)
    if trace_dir_path.is_absolute():
        return trace_dir_path
    return root / trace_dir_raw


def ensure_trace_directories(config: RuntimeConfig) -> None:
    config.trace_dir.mkdir(parents=True, exist_ok=True)
    (config.trace_dir / "async").mkdir(parents=True, exist_ok=True)


def _regex_rule_configs(value: object) -> list[RegexRuleConfig]:
    if not isinstance(value, list):
        return []

    raw_items = cast(list[object], value)
    regex_rules: list[RegexRuleConfig] = []
    for item in raw_items:
        if isinstance(item, dict):
            data = _object_dict(cast(dict[object, object], item))
            regex_rules.append(
                RegexRuleConfig(
                    rule_id=_string_value(data.get("rule_id")),
                    title=_string_value(data.get("title")),
                    severity=_string_value(data.get("severity"), "MEDIUM"),
                    events=_string_list(data.get("events")) or ["PreToolUse"],
                    target=_string_value(data.get("target"), "content"),
                    action=_string_value(data.get("action"), "deny"),
                    message=_string_value(data.get("message")),
                    additional_context=(
                        _string_value(data.get("additional_context"))
                        if data.get("additional_context") is not None
                        else None
                    ),
                    patterns=_string_list(data.get("patterns")),
                    path_globs=_string_list(data.get("path_globs")),
                    exclude_path_globs=_string_list(data.get("exclude_path_globs")),
                    tool_matchers=_string_list(data.get("tool_matchers")),
                    case_sensitive=_bool_value(data.get("case_sensitive"), False),
                    multiline=_bool_value(data.get("multiline"), True),
                )
            )
    return regex_rules


@dataclass(frozen=True, slots=True)
class _RepoQualityGateSettings:
    thresholds: dict[str, object]
    enabled_rules: dict[str, bool]
    post_edit_quality: dict[str, object]
    async_jobs: dict[str, object]
    disabled_rules: list[str]
    severity_overrides: dict[str, str]


@dataclass(frozen=True, slots=True)
class _PostEditQualitySettings:
    enabled: bool
    block_on_failure: bool
    commands: dict[str, list[str]]


@dataclass(frozen=True, slots=True)
class _AsyncJobSettings:
    enabled: bool
    commands: dict[str, list[str]]


@dataclass(frozen=True, slots=True)
class _PythonRuntimeSettings:
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


def _repo_quality_gate_settings(repo_root: Path) -> _RepoQualityGateSettings:
    toml_data = _load_toml(repo_root)
    qg_section = _object_dict(toml_data.get("quality_gate", {}))
    return _RepoQualityGateSettings(
        thresholds=_object_dict(toml_data.get("thresholds", {})),
        enabled_rules={
            str(key): bool(value)
            for key, value in _object_dict(toml_data.get("enabled_rules", {})).items()
        },
        post_edit_quality=_object_dict(toml_data.get("post_edit_quality", {})),
        async_jobs=_object_dict(toml_data.get("async_jobs", {})),
        disabled_rules=_string_list(qg_section.get("disabled_rules", [])),
        severity_overrides={
            str(key): str(value)
            for key, value in _object_dict(
                qg_section.get("severity_overrides", {})
            ).items()
        },
    )


def _enabled_rule_settings(
    raw: dict[str, object], repo_settings: _RepoQualityGateSettings
) -> dict[str, bool]:
    enabled_rules = {
        str(key): bool(value)
        for key, value in _object_dict(raw.get("enabled_rules", {})).items()
    }
    enabled_rules.update(repo_settings.enabled_rules)
    return enabled_rules


def _post_edit_quality_settings(
    raw: dict[str, object], repo_settings: _RepoQualityGateSettings
) -> _PostEditQualitySettings:
    post_edit_quality = _object_dict(raw.get("post_edit_quality", {}))
    repo_post_edit_quality = repo_settings.post_edit_quality
    return _PostEditQualitySettings(
        enabled=_bool_value(
            repo_post_edit_quality.get("enabled", post_edit_quality.get("enabled")),
            False,
        ),
        block_on_failure=_bool_value(
            repo_post_edit_quality.get(
                "block_on_failure", post_edit_quality.get("block_on_failure")
            ),
            True,
        ),
        commands=_command_map(
            repo_post_edit_quality.get(
                "commands_by_language",
                post_edit_quality.get("commands_by_language", {}),
            )
        ),
    )


def _async_job_settings(
    raw: dict[str, object], repo_settings: _RepoQualityGateSettings
) -> _AsyncJobSettings:
    async_jobs = _object_dict(raw.get("async_jobs", {}))
    repo_async_jobs = repo_settings.async_jobs
    return _AsyncJobSettings(
        enabled=_bool_value(
            repo_async_jobs.get("enabled", async_jobs.get("enabled")),
            False,
        ),
        commands=_command_map(
            repo_async_jobs.get(
                "commands_by_language",
                async_jobs.get("commands_by_language", {}),
            )
        ),
    )


def _runtime_default_int(key: str) -> int:
    return int(RUNTIME_POLICY_DEFAULTS[key])


def _threshold_int(thresholds: dict[str, object], key: str) -> int:
    return _int_value(thresholds.get(key), _runtime_default_int(key))


def _threshold_float(thresholds: dict[str, object], key: str) -> float:
    return _float_value(thresholds.get(key), float(RUNTIME_POLICY_DEFAULTS[key]))


@dataclass(frozen=True, slots=True)
class _PythonAstThresholdKeys:
    threshold: str
    python_ast: str
    default: str


def _python_ast_threshold_int(
    thresholds: dict[str, object],
    python_ast: dict[str, object],
    keys: _PythonAstThresholdKeys,
) -> int:
    value = thresholds.get(
        keys.threshold,
        python_ast.get(keys.python_ast, RUNTIME_POLICY_DEFAULTS[keys.default]),
    )
    return _int_value(value, _runtime_default_int(keys.default))


def _python_runtime_settings(
    raw: dict[str, object], repo_settings: _RepoQualityGateSettings
) -> _PythonRuntimeSettings:
    python_ast = _object_dict(raw.get("python_ast", {}))
    thresholds = repo_settings.thresholds
    return _PythonRuntimeSettings(
        ast_enabled=_bool_value(python_ast.get("enabled"), True),
        max_parse_chars=_int_value(
            python_ast.get("max_parse_chars"), _runtime_default_int("max_parse_chars")
        ),
        long_method_lines=_python_ast_threshold_int(
            thresholds,
            python_ast,
            _PythonAstThresholdKeys("max_method_lines", "long_method_lines", "long_method_lines"),
        ),
        long_parameter_limit=_python_ast_threshold_int(
            thresholds,
            python_ast,
            _PythonAstThresholdKeys("max_params", "long_parameter_limit", "long_parameter_limit"),
        ),
        max_complexity=_threshold_int(thresholds, "max_complexity"),
        max_nesting_depth=_threshold_int(thresholds, "max_nesting_depth"),
        max_god_class_methods=_threshold_int(thresholds, "max_god_class_methods"),
        max_line_length=_threshold_int(thresholds, "max_line_length"),
        feature_envy_threshold=_threshold_float(thresholds, "feature_envy_threshold"),
        feature_envy_min_accesses=_threshold_int(thresholds, "feature_envy_min_accesses"),
        import_fanout_limit=_threshold_int(thresholds, "import_fanout_limit"),
    )


def _merge_config(
    actual_root: Path,
    raw: dict[str, object],
    repo_root: Path,
) -> RuntimeConfig:
    repo_settings = _repo_quality_gate_settings(repo_root)
    post_edit = _post_edit_quality_settings(raw, repo_settings)
    async_jobs = _async_job_settings(raw, repo_settings)
    python_runtime = _python_runtime_settings(raw, repo_settings)

    return RuntimeConfig(
        root=actual_root,
        repo_root=repo_root,
        trace_dir=_resolve_trace_dir(raw, actual_root),
        prompt_context_files=_string_list(raw.get("prompt_context_files", [])),
        search_reminder_message=_string_value(raw.get("search_reminder_message")).strip(),
        protected_paths=_string_list(raw.get("protected_paths", [])),
        sensitive_path_patterns=_string_list(raw.get("sensitive_path_patterns", [])),
        system_path_prefixes=_string_list(raw.get("system_path_prefixes", [])),
        python_ast_enabled=python_runtime.ast_enabled,
        python_ast_max_parse_chars=python_runtime.max_parse_chars,
        python_long_method_lines=python_runtime.long_method_lines,
        python_long_parameter_limit=python_runtime.long_parameter_limit,
        post_edit_quality_enabled=post_edit.enabled,
        post_edit_quality_block_on_failure=post_edit.block_on_failure,
        post_edit_quality_commands=post_edit.commands,
        async_jobs_enabled=async_jobs.enabled,
        async_jobs_commands=async_jobs.commands,
        python_max_complexity=python_runtime.max_complexity,
        python_max_nesting_depth=python_runtime.max_nesting_depth,
        python_max_god_class_methods=python_runtime.max_god_class_methods,
        python_max_line_length=python_runtime.max_line_length,
        python_feature_envy_threshold=python_runtime.feature_envy_threshold,
        python_feature_envy_min_accesses=python_runtime.feature_envy_min_accesses,
        python_import_fanout_limit=python_runtime.import_fanout_limit,
        skip_paths=_string_list(raw.get("skip_paths", [])),
        skip_if_file_exists=_string_list(
            raw.get("skip_if_file_exists", list(_DISABLE_SENTINELS))
        ),
        disabled_rules=repo_settings.disabled_rules,
        severity_overrides=repo_settings.severity_overrides,
        enabled_rules=_enabled_rule_settings(raw, repo_settings),
        regex_rules=_regex_rule_configs(raw.get("regex_rules", [])),
    )
