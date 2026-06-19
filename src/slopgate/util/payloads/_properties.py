from __future__ import annotations

from functools import cached_property
from pathlib import Path

from slopgate._types import ObjectDict, object_dict
from slopgate.constants import SESSION_ID
from slopgate.models import ContentTarget, RuntimeConfig
from slopgate.util import logger

from ._basic import detect_language, first_present, shell_kind_for_tool
from ._intent import (
    ToolIntent,
    candidate_path_source,
    is_mutating_tool_use,
    is_read_only_tool_use,
    platform_event_name,
    tool_intent,
    tool_intent_reason,
)
from ._shell import shell_command_paths
from ._shell_content import shell_content_targets
from .targets import (
    ctx_execute_content_target,
    direct_candidate_paths,
    multi_edit_candidate_paths,
    multi_edit_content_targets,
    patch_candidate_paths,
    patch_content_targets,
    tool_input_content_target,
    tool_input_path,
    tool_response_candidate_paths,
    unique_content_targets,
    unique_paths,
)

UNSET_LOG_VALUE = "unset"


class _CoreHookPayloadProperties:
    payload: ObjectDict
    config: RuntimeConfig

    @cached_property
    def event_name(self) -> str:
        event_name = str(self.payload.get("hook_event_name", "")).strip()
        logger.info(
            "hook payload event resolved",
            event_name=event_name or UNSET_LOG_VALUE,
            tool_name=self.tool_name or UNSET_LOG_VALUE,
            session_id=self.session_id or UNSET_LOG_VALUE,
        )
        return event_name

    @cached_property
    def tool_name(self) -> str:
        value = self.payload.get("tool_name")
        if isinstance(value, str) and value.strip():
            return value.strip()
        fallback = self.payload.get("tool")
        if isinstance(fallback, str):
            return fallback.strip()
        return ""

    @cached_property
    def tool_input(self) -> ObjectDict:
        return object_dict(self.payload.get("tool_input"))

    @cached_property
    def cwd(self) -> Path:
        value = self.payload.get("cwd")
        if isinstance(value, str) and value.strip():
            return Path(value).resolve()
        return self.config.repo_root

    @cached_property
    def session_id(self) -> str:
        value = self.payload.get(SESSION_ID)
        return str(value).strip() if value is not None else ""

    @cached_property
    def user_prompt(self) -> str:
        value = self.payload.get("prompt")
        return value if isinstance(value, str) else ""


class _ShellHookPayloadProperties(_CoreHookPayloadProperties):
    @cached_property
    def bash_command(self) -> str:
        return self.shell_command

    @cached_property
    def shell_kind(self) -> str | None:
        return shell_kind_for_tool(self.tool_name)

    @cached_property
    def shell_command(self) -> str:
        if self.shell_kind is None:
            return ""
        return first_present(
            self.tool_input,
            ("command", "script", "cmd", "powershell_command", "pwsh_command"),
            strip=False,
        )


class _TargetHookPayloadProperties(_ShellHookPayloadProperties):
    @cached_property
    def tool_intent(self) -> ToolIntent:
        return tool_intent(self)

    @cached_property
    def intent_reason(self) -> str:
        return tool_intent_reason(self)

    @cached_property
    def read_only(self) -> bool:
        return is_read_only_tool_use(self)

    @cached_property
    def mutating(self) -> bool:
        return is_mutating_tool_use(self)

    @cached_property
    def candidate_path_source(self) -> str:
        return candidate_path_source(self)

    @cached_property
    def platform_event_name(self) -> str:
        return platform_event_name(self)

    @cached_property
    def content_targets(self) -> list[ContentTarget]:
        targets: list[ContentTarget] = []
        fallback_path = tool_input_path(self.tool_input, self.payload)
        input_target = tool_input_content_target(self.tool_input, fallback_path)
        if input_target is not None:
            targets.append(input_target)
        ctx_target = ctx_execute_content_target(self.tool_name, self.tool_input)
        if ctx_target is not None:
            targets.append(ctx_target)
        targets.extend(multi_edit_content_targets(self.tool_input, fallback_path))
        targets.extend(patch_content_targets(self.tool_input))
        if self.shell_command:
            targets.extend(shell_content_targets(self.shell_command))
        return unique_content_targets(targets)

    @cached_property
    def candidate_paths(self) -> list[str]:
        values = [
            *direct_candidate_paths(self.payload, self.tool_input),
            *multi_edit_candidate_paths(self.tool_input),
            *patch_candidate_paths(self.tool_input),
            *tool_response_candidate_paths(self.payload),
        ]
        if self.shell_command:
            values.extend(shell_command_paths(self.shell_command, self.shell_kind))
        return unique_paths(values)

    @cached_property
    def languages(self) -> set[str]:
        languages: set[str] = set()
        for path_value in self.candidate_paths:
            language = detect_language(path_value)
            if language:
                languages.add(language)
        return languages


class HookPayloadProperties(_TargetHookPayloadProperties):
    pass
