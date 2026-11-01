"""Shared HookContext builders for guard-rule tests."""

from __future__ import annotations

from pathlib import Path

from slopgate.config import load_config
from slopgate.context import HookContext
from slopgate.state import HookStateStore
from slopgate.trace import TraceWriter
from slopgate.util.payloads import HookPayload

from tests.integration.config_override_support import (
    GuardRuleConfigOverrides,
    apply_guard_rule_config_overrides,
)


def context_for_payload(
    tmp_path: Path,
    payload: dict[str, object],
    config_overrides: GuardRuleConfigOverrides | None = None,
) -> HookContext:
    config = load_config(
        root=tmp_path,
        repo_root=tmp_path,
        ensure_enrollment=False,
        ensure_trace=False,
    )
    if config_overrides is not None:
        config = apply_guard_rule_config_overrides(config, config_overrides)
    trace = TraceWriter(tmp_path / ".slopgate" / "trace")
    return HookContext(
        payload=HookPayload(payload, config),
        config=config,
        trace=trace,
        state=HookStateStore(trace.trace_dir),
    )


def write_payload(
    file_path: str, content: str, event: str = "PreToolUse"
) -> dict[str, object]:
    return {
        "session_id": "test-session",
        "hook_event_name": event,
        "tool_name": "Write",
        "tool_input": {"file_path": file_path, "content": content},
    }
