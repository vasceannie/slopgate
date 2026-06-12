from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from slopgate.models import RegexRuleConfig, RuntimeConfig
from slopgate.policy_defaults import RUNTIME_POLICY_DEFAULTS

from ._coerce import (
    bool_value,
    command_map,
    float_value,
    int_value,
    object_dict,
    string_list,
    string_value,
)
from ._io import load_toml
from ._repo import DISABLE_SENTINELS


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
            data = object_dict(cast(dict[object, object], item))
            regex_rules.append(
                RegexRuleConfig(
                    rule_id=string_value(data.get("rule_id")),
                    title=string_value(data.get("title")),
                    severity=string_value(data.get("severity"), "MEDIUM"),
                    events=string_list(data.get("events")) or ["PreToolUse"],
                    target=string_value(data.get("target"), "content"),
                    action=string_value(data.get("action"), "deny"),
                    message=string_value(data.get("message")),
                    additional_context=(
                        string_value(data.get("additional_context"))
                        if data.get("additional_context") is not None
                        else None
                    ),
                    patterns=string_list(data.get("patterns")),
                    path_globs=string_list(data.get("path_globs")),
                    exclude_path_globs=string_list(data.get("exclude_path_globs")),
                    tool_matchers=string_list(data.get("tool_matchers")),
                    case_sensitive=bool_value(data.get("case_sensitive"), False),
                    multiline=bool_value(data.get("multiline"), True),
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


def _repo_slopgate_settings(repo_root: Path) -> _RepoQualityGateSettings:
    toml_data = load_toml(repo_root)
    qg_section = object_dict(toml_data.get("slopgate", {}))
    return _RepoQualityGateSettings(
        thresholds=object_dict(toml_data.get("thresholds", {})),
        enabled_rules={
            key: bool(value)
            for key, value in object_dict(toml_data.get("enabled_rules", {})).items()
        },
        post_edit_quality=object_dict(toml_data.get("post_edit_quality", {})),
        async_jobs=object_dict(toml_data.get("async_jobs", {})),
        disabled_rules=string_list(qg_section.get("disabled_rules", [])),
        severity_overrides={
            key: value
            for key, value in object_dict(
                qg_section.get("severity_overrides", {})
            ).items()
            if isinstance(value, str)
        },
    )


def _enabled_rule_settings(
    raw: dict[str, object], repo_settings: _RepoQualityGateSettings
) -> dict[str, bool]:
    enabled_rules = {
        key: bool(value)
        for key, value in object_dict(raw.get("enabled_rules", {})).items()
    }
    enabled_rules.update(repo_settings.enabled_rules)
    return enabled_rules


def _post_edit_quality_settings(
    raw: dict[str, object], repo_settings: _RepoQualityGateSettings
) -> _PostEditQualitySettings:
    post_edit_quality = object_dict(raw.get("post_edit_quality", {}))
    repo_post_edit_quality = repo_settings.post_edit_quality
    return _PostEditQualitySettings(
        enabled=bool_value(
            repo_post_edit_quality.get("enabled", post_edit_quality.get("enabled")),
            False,
        ),
        block_on_failure=bool_value(
            repo_post_edit_quality.get(
                "block_on_failure", post_edit_quality.get("block_on_failure")
            ),
            True,
        ),
        commands=command_map(
            repo_post_edit_quality.get(
                "commands_by_language",
                post_edit_quality.get("commands_by_language", {}),
            )
        ),
    )


def _async_job_settings(
    raw: dict[str, object], repo_settings: _RepoQualityGateSettings
) -> _AsyncJobSettings:
    async_jobs = object_dict(raw.get("async_jobs", {}))
    repo_async_jobs = repo_settings.async_jobs
    return _AsyncJobSettings(
        enabled=bool_value(
            repo_async_jobs.get("enabled", async_jobs.get("enabled")),
            False,
        ),
        commands=command_map(
            repo_async_jobs.get(
                "commands_by_language",
                async_jobs.get("commands_by_language", {}),
            )
        ),
    )


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


def _python_runtime_settings(
    raw: dict[str, object], repo_settings: _RepoQualityGateSettings
) -> _PythonRuntimeSettings:
    python_ast = object_dict(raw.get("python_ast", {}))
    thresholds = repo_settings.thresholds
    return _PythonRuntimeSettings(
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


def merge_config(
    actual_root: Path,
    raw: dict[str, object],
    repo_root: Path,
) -> RuntimeConfig:
    repo_settings = _repo_slopgate_settings(repo_root)
    post_edit = _post_edit_quality_settings(raw, repo_settings)
    async_jobs = _async_job_settings(raw, repo_settings)
    python_runtime = _python_runtime_settings(raw, repo_settings)

    return RuntimeConfig(
        root=actual_root,
        repo_root=repo_root,
        trace_dir=_resolve_trace_dir(raw, actual_root),
        prompt_context_files=string_list(raw.get("prompt_context_files", [])),
        search_reminder_message=string_value(
            raw.get("search_reminder_message")
        ).strip(),
        protected_paths=string_list(raw.get("protected_paths", [])),
        sensitive_path_patterns=string_list(raw.get("sensitive_path_patterns", [])),
        system_path_prefixes=string_list(raw.get("system_path_prefixes", [])),
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
        skip_paths=string_list(raw.get("skip_paths", [])),
        skip_if_file_exists=string_list(
            raw.get("skip_if_file_exists", list(DISABLE_SENTINELS))
        ),
        disabled_rules=repo_settings.disabled_rules,
        severity_overrides=repo_settings.severity_overrides,
        enabled_rules=_enabled_rule_settings(raw, repo_settings),
        regex_rules=_regex_rule_configs(raw.get("regex_rules", [])),
    )
