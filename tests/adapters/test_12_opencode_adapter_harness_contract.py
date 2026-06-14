from __future__ import annotations

from tests.test_adapters import (
    ObjectDict,
    OpenCodeAdapter,
    RuleFinding,
    Severity,
    pytest,
    require_rendered,
)
from slopgate.adapters.opencode import OPENCODE_EVENT_MAP

CONTRACT_SESSION_ID = "opencode-contract"
CONTRACT_CWD = "/tmp/slopgate-opencode-contract"
CONTRACT_CONTEXT = "surface advisory context"

OPENCODE_NORMALIZATION_EVENT_CASES = (
    pytest.param("tool.execute.before", "PreToolUse", id="tool_before"),
    pytest.param("tool.execute.after", "PostToolUse", id="tool_after"),
    pytest.param("file.edited", "PostToolUse", id="file_edited"),
    pytest.param("permission.asked", "PermissionRequest", id="permission_asked"),
    pytest.param("permission.replied", "PermissionReplied", id="permission_replied"),
    pytest.param("session.created", "SessionStart", id="session_created"),
    pytest.param("session.compacted", "PostCompact", id="session_compacted"),
    pytest.param("session.idle", "Stop", id="session_idle"),
    pytest.param("session.error", "SessionError", id="session_error"),
    pytest.param("session.status", "SessionStatus", id="session_status"),
    pytest.param("shell.env", "ShellEnv", id="shell_env"),
    pytest.param("command.executed", "CommandExecuted", id="command_executed"),
)

OPENCODE_RENDERED_SURFACE_CASES = (
    pytest.param("tool.execute.before", "block", None, id="pretool_blocks"),
    pytest.param("permission.asked", "block", None, id="permission_blocks"),
    pytest.param("tool.execute.after", "block", None, id="posttool_blocks"),
    pytest.param("file.edited", "block", None, id="file_edited_blocks"),
    pytest.param("session.idle", "continue", None, id="stop_is_advisory_continue"),
    pytest.param(
        "session.created", "context", CONTRACT_CONTEXT, id="session_start_context"
    ),
)

OPENCODE_ADVISORY_NO_OUTPUT_CASES = (
    pytest.param("command.executed", id="command_executed"),
    pytest.param("permission.replied", id="permission_replied"),
    pytest.param("session.compacted", id="session_compacted"),
    pytest.param("session.error", id="session_error"),
    pytest.param("session.status", id="session_status"),
    pytest.param("shell.env", id="shell_env"),
)


def _raw_opencode_payload(native_event: str) -> dict[str, object]:
    return {
        "hook_event_name": native_event,
        "cwd": CONTRACT_CWD,
        "session_id": CONTRACT_SESSION_ID,
    }


def _render_contract_output(native_event: str, context: str | None) -> ObjectDict:
    adapter = OpenCodeAdapter()
    normalized = adapter.normalize_payload(_raw_opencode_payload(native_event))
    return require_rendered(
        adapter.render_output(
            str(normalized["hook_event_name"]),
            [
                RuleFinding(
                    rule_id="OPENCODE-CONTRACT-001",
                    title="OpenCode contract",
                    severity=Severity.HIGH,
                    decision="block",
                    message="OpenCode harness contract violation",
                    additional_context=context,
                )
            ],
            decision="block",
            context=context,
            updated_input={},
        )
    )


@pytest.mark.parametrize(
    ("native_event", "canonical_event"), OPENCODE_NORMALIZATION_EVENT_CASES
)
def test_opencode_harness_events_match_adapter_normalization_contract(
    native_event: str, canonical_event: str
) -> None:
    normalized = OpenCodeAdapter().normalize_payload(
        _raw_opencode_payload(native_event)
    )

    assert OPENCODE_EVENT_MAP[native_event] == canonical_event, (
        f"{native_event} should be registered in OPENCODE_EVENT_MAP"
    )
    assert normalized["hook_event_name"] == canonical_event, (
        f"{native_event} should normalize to {canonical_event}"
    )
    assert normalized["opencode_hook_event"] == native_event, (
        "native OpenCode event should remain available for trace attribution"
    )


def test_opencode_file_edited_contract_synthesizes_write_tool() -> None:
    normalized = OpenCodeAdapter().normalize_payload(
        _raw_opencode_payload("file.edited") | {"path": "src/app.py"}
    )

    assert normalized["hook_event_name"] == "PostToolUse", (
        "file.edited should route through the canonical post-tool surface"
    )
    assert normalized["tool_name"] == "Write", (
        "file.edited should synthesize Write when OpenCode omits a tool name"
    )
    assert normalized["opencode_hook_event"] == "file.edited", (
        "file.edited should stay available for platform-specific trace attribution"
    )


@pytest.mark.parametrize(
    ("native_event", "expected_action", "context"), OPENCODE_RENDERED_SURFACE_CASES
)
def test_opencode_harness_events_render_expected_surface_shape(
    native_event: str, expected_action: str, context: str | None
) -> None:
    output = _render_contract_output(native_event, context)

    assert output["action"] == expected_action, (
        f"{native_event} should render the OpenCode harness action contract"
    )
    assert "hookSpecificOutput" not in output, (
        f"{native_event} should not render Claude/Codex hookSpecificOutput"
    )


@pytest.mark.parametrize("native_event", OPENCODE_ADVISORY_NO_OUTPUT_CASES)
def test_opencode_advisory_events_have_no_blocking_render_surface(
    native_event: str,
) -> None:
    normalized = OpenCodeAdapter().normalize_payload(
        _raw_opencode_payload(native_event)
    )
    output = OpenCodeAdapter().render_output(
        str(normalized["hook_event_name"]),
        [
            RuleFinding(
                rule_id="OPENCODE-ADVISORY-001",
                title="OpenCode advisory contract",
                severity=Severity.LOW,
                decision="block",
                message="advisory event",
            )
        ],
        decision="block",
        context=None,
        updated_input={},
    )

    assert output is None, f"{native_event} should not claim a blocking surface"
