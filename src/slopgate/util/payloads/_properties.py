from __future__ import annotations

from functools import cached_property
from pathlib import Path

from slopgate._types import ObjectDict, object_dict
from slopgate.models import ContentTarget, RuntimeConfig

from ._basic import detect_language, first_present, shell_kind_for_tool
from ._shell import shell_command_paths
from ._targets import (
    _direct_candidate_paths,
    _multi_edit_candidate_paths,
    _multi_edit_content_targets,
    _patch_candidate_paths,
    _patch_content_targets,
    _tool_input_content_target,
    _tool_input_path,
    _tool_response_candidate_paths,
    _unique_content_targets,
    _unique_paths,
)


class _CoreHookPayloadProperties:
    payload: ObjectDict
    config: RuntimeConfig

    @cached_property
    def event_name(self) -> str:
        return str(self.payload.get("hook_event_name", "")).strip()

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
        value = self.payload.get("session_id")
        return str(value).strip() if value is not None else ""

    @cached_property
    def user_prompt(self) -> str:
        value = self.payload.get("prompt")
        return str(value) if isinstance(value, str) else ""


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
    def content_targets(self) -> list[ContentTarget]:
        targets: list[ContentTarget] = []
        fallback_path = _tool_input_path(self.tool_input, self.payload)
        input_target = _tool_input_content_target(self.tool_input, fallback_path)
        if input_target is not None:
            targets.append(input_target)
        targets.extend(_multi_edit_content_targets(self.tool_input, fallback_path))
        targets.extend(_patch_content_targets(self.tool_input))
        return _unique_content_targets(targets)

    @cached_property
    def candidate_paths(self) -> list[str]:
        values = [
            *_direct_candidate_paths(self.payload, self.tool_input),
            *_multi_edit_candidate_paths(self.tool_input),
            *_patch_candidate_paths(self.tool_input),
            *_tool_response_candidate_paths(self.payload),
        ]
        if self.shell_command:
            values.extend(shell_command_paths(self.shell_command, self.shell_kind))
        return _unique_paths(values)

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
