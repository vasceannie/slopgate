from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from slopgate.constants import (
    METADATA_CONTENT,
    METADATA_RULE_ID,
    METADATA_SLOPGATE,
    METADATA_TARGET,
)
from slopgate.models import (
    FailureProfileConfig,
    RegexRuleConfig,
    RuleSurfaceConfig,
    RuntimeConfig,
)

from ._coerce import (
    bool_value,
    command_map,
    object_dict,
    string_list,
    string_value,
)
from ._io import load_toml
from ._failure_profile import failure_profile_config
from ._python_runtime import PythonRuntimeSettings, python_runtime_settings
from ._repo import DISABLE_SENTINELS
from ._rule_surfaces import merge_rule_surfaces, rule_surface_configs


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
                    rule_id=string_value(data.get(METADATA_RULE_ID)),
                    title=string_value(data.get("title")),
                    severity=string_value(data.get("severity"), "MEDIUM"),
                    events=string_list(data.get("events")) or ["PreToolUse"],
                    target=string_value(data.get(METADATA_TARGET), METADATA_CONTENT),
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
    rule_surfaces: dict[str, RuleSurfaceConfig]
    post_edit_quality: dict[str, object]
    hook_guidance: dict[str, object]
    async_jobs: dict[str, object]
    disabled_rules: list[str]
    severity_overrides: dict[str, str]
    failure_profile: FailureProfileConfig


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
class _HookGuidanceSettings:
    project_logger_import: str
    project_logger_usage: str
    quality_check_command: str


@dataclass(frozen=True, slots=True)
class _ResolvedRuntimeSettings:
    repo: _RepoQualityGateSettings
    post_edit: _PostEditQualitySettings
    hook_guidance: _HookGuidanceSettings
    async_jobs: _AsyncJobSettings
    python: PythonRuntimeSettings


def _repo_slopgate_settings(repo_root: Path) -> _RepoQualityGateSettings:
    toml_data = load_toml(repo_root)
    qg_section = object_dict(toml_data.get(METADATA_SLOPGATE, {}))
    return _RepoQualityGateSettings(
        thresholds=object_dict(toml_data.get("thresholds", {})),
        enabled_rules={
            key: bool(value)
            for key, value in object_dict(toml_data.get("enabled_rules", {})).items()
        },
        rule_surfaces=rule_surface_configs(toml_data.get("rule_surfaces")),
        post_edit_quality=object_dict(toml_data.get("post_edit_quality", {})),
        hook_guidance=object_dict(toml_data.get("hook_guidance", {})),
        async_jobs=object_dict(toml_data.get("async_jobs", {})),
        disabled_rules=string_list(qg_section.get("disabled_rules", [])),
        severity_overrides={
            key: value
            for key, value in object_dict(
                qg_section.get("severity_overrides", {})
            ).items()
            if isinstance(value, str)
        },
        failure_profile=failure_profile_config(toml_data),
    )


def _hook_guidance_settings(
    raw: dict[str, object], repo_settings: _RepoQualityGateSettings
) -> _HookGuidanceSettings:
    hook_guidance = object_dict(raw.get("hook_guidance", {}))
    repo_hook_guidance = repo_settings.hook_guidance
    return _HookGuidanceSettings(
        project_logger_import=string_value(
            repo_hook_guidance.get(
                "project_logger_import",
                hook_guidance.get("project_logger_import", ""),
            )
        ).strip(),
        project_logger_usage=string_value(
            repo_hook_guidance.get(
                "project_logger_usage",
                hook_guidance.get("project_logger_usage", ""),
            )
        ).strip(),
        quality_check_command=string_value(
            repo_hook_guidance.get(
                "quality_check_command",
                hook_guidance.get("quality_check_command", "slopgate lint check"),
            ),
            "slopgate lint check",
        ).strip()
        or "slopgate lint check",
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


def _rule_surface_settings(
    raw: dict[str, object], repo_settings: _RepoQualityGateSettings
) -> dict[str, RuleSurfaceConfig]:
    global_surfaces = rule_surface_configs(raw.get("rule_surfaces"))
    return merge_rule_surfaces(global_surfaces, repo_settings.rule_surfaces)


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


def _resolved_runtime_settings(
    raw: dict[str, object], repo_root: Path
) -> _ResolvedRuntimeSettings:
    repo = _repo_slopgate_settings(repo_root)
    return _ResolvedRuntimeSettings(
        repo=repo,
        post_edit=_post_edit_quality_settings(raw, repo),
        hook_guidance=_hook_guidance_settings(raw, repo),
        async_jobs=_async_job_settings(raw, repo),
        python=python_runtime_settings(raw, repo.thresholds),
    )


def merge_config(
    actual_root: Path,
    raw: dict[str, object],
    repo_root: Path,
) -> RuntimeConfig:
    settings = _resolved_runtime_settings(raw, repo_root)

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
        python_ast_enabled=settings.python.ast_enabled,
        python_ast_max_parse_chars=settings.python.max_parse_chars,
        python_long_method_lines=settings.python.long_method_lines,
        python_long_parameter_limit=settings.python.long_parameter_limit,
        post_edit_quality_enabled=settings.post_edit.enabled,
        post_edit_quality_block_on_failure=settings.post_edit.block_on_failure,
        post_edit_quality_commands=settings.post_edit.commands,
        hook_project_logger_import=settings.hook_guidance.project_logger_import,
        hook_project_logger_usage=settings.hook_guidance.project_logger_usage,
        hook_quality_check_command=settings.hook_guidance.quality_check_command,
        async_jobs_enabled=settings.async_jobs.enabled,
        async_jobs_commands=settings.async_jobs.commands,
        python_max_complexity=settings.python.max_complexity,
        python_max_nesting_depth=settings.python.max_nesting_depth,
        python_max_god_class_methods=settings.python.max_god_class_methods,
        python_max_line_length=settings.python.max_line_length,
        python_feature_envy_threshold=settings.python.feature_envy_threshold,
        python_feature_envy_min_accesses=settings.python.feature_envy_min_accesses,
        python_import_fanout_limit=settings.python.import_fanout_limit,
        skip_paths=string_list(raw.get("skip_paths", [])),
        skip_if_file_exists=string_list(
            raw.get("skip_if_file_exists", list(DISABLE_SENTINELS))
        ),
        disabled_rules=settings.repo.disabled_rules,
        severity_overrides=settings.repo.severity_overrides,
        enabled_rules=_enabled_rule_settings(raw, settings.repo),
        rule_surfaces=_rule_surface_settings(raw, settings.repo),
        regex_rules=_regex_rule_configs(raw.get("regex_rules", [])),
        failure_profile=settings.repo.failure_profile,
    )
