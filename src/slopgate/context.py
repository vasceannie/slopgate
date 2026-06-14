from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from slopgate._types import ObjectDict, ObjectMapping
from slopgate.config import load_config
from slopgate.models import ContentTarget, RuntimeConfig
from slopgate.state import HookStateStore
from slopgate.trace import TraceWriter
from slopgate.util.payloads import HookPayload, ToolIntent


class _CoreContextProperties:
    payload: HookPayload

    @property
    def event_name(self) -> str:
        return self.payload.event_name

    @property
    def tool_name(self) -> str:
        return self.payload.tool_name

    @property
    def tool_input(self) -> ObjectDict:
        return self.payload.tool_input

    @property
    def user_prompt(self) -> str:
        return self.payload.user_prompt

    @property
    def cwd(self) -> Path:
        return self.payload.cwd

    @property
    def session_id(self) -> str:
        return self.payload.session_id


class _ShellContextProperties(_CoreContextProperties):
    @property
    def bash_command(self) -> str:
        return self.payload.bash_command

    @property
    def shell_command(self) -> str:
        return self.payload.shell_command

    @property
    def shell_kind(self) -> str | None:
        return self.payload.shell_kind


class _TargetContextProperties(_ShellContextProperties):
    @property
    def content_targets(self) -> list[ContentTarget]:
        return self.payload.content_targets

    @property
    def candidate_paths(self) -> list[str]:
        return self.payload.candidate_paths

    @property
    def languages(self) -> set[str]:
        return self.payload.languages

    @property
    def tool_intent(self) -> ToolIntent:
        return self.payload.tool_intent

    @property
    def intent_reason(self) -> str:
        return self.payload.intent_reason

    @property
    def read_only(self) -> bool:
        return self.payload.read_only

    @property
    def mutating(self) -> bool:
        return self.payload.mutating

    @property
    def candidate_path_source(self) -> str:
        return self.payload.candidate_path_source

    @property
    def platform_event_name(self) -> str:
        return self.payload.platform_event_name


@dataclass(slots=True)
class HookContext(_TargetContextProperties):
    payload: HookPayload
    config: RuntimeConfig
    trace: TraceWriter
    state: HookStateStore


def build_context(payload_dict: ObjectMapping) -> HookContext:
    payload_cwd = payload_dict.get("cwd")
    repo_root = (
        Path(payload_cwd).resolve()
        if isinstance(payload_cwd, str) and payload_cwd.strip()
        else None
    )
    config = load_config(repo_root=repo_root)
    trace = TraceWriter(config.trace_dir)
    payload = HookPayload(payload_dict, config)
    state = HookStateStore(config.trace_dir)
    return HookContext(payload=payload, config=config, trace=trace, state=state)
