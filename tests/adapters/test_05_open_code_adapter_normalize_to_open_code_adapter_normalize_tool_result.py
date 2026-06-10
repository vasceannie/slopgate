from __future__ import annotations

from tests.test_adapters import (
    ObjectDict,
    OpenCodeAdapter,
    RuleFinding,
    Severity,
    require_rendered,
)


class TestOpenCodeAdapterNormalize:
    """Event name and tool name normalization."""

    def test_normalize_maps_event_name(self) -> None:
        adapter = OpenCodeAdapter()
        raw = {
            "hook_event_name": "tool.execute.before",
            "tool_name": "bash",
            "tool_input": {"command": "ls"},
            "cwd": "/tmp",
            "session_id": "opencode-123-abc",
        }
        canonical = adapter.normalize_payload(raw)
        assert canonical["hook_event_name"] == "PreToolUse", "event name not mapped"
        assert canonical["tool_name"] == "Bash", "tool name not capitalized"

    def test_normalize_preserves_already_canonical(self) -> None:
        adapter = OpenCodeAdapter()
        raw = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/x.py", "content": "print(1)"},
            "cwd": "/tmp",
            "session_id": "oc2",
        }
        canonical = adapter.normalize_payload(raw)
        # Already uppercase, already canonical event name
        assert canonical["hook_event_name"] == "PreToolUse", "canonical event changed"
        assert canonical["tool_name"] == "Write", "canonical tool name changed"

    def test_normalize_maps_known_lowercase_tool_alias(self) -> None:
        adapter = OpenCodeAdapter()
        raw: ObjectDict = {
            "hook_event_name": "tool.execute.before",
            "tool_name": "write",
            "tool_input": {},
            "cwd": "/tmp",
            "session_id": "oc3",
        }
        canonical = adapter.normalize_payload(raw)
        assert canonical["tool_name"] == "Write", "known lowercase alias not mapped"

    def test_normalize_preserves_unknown_lowercase_tool_name(self) -> None:
        adapter = OpenCodeAdapter()
        raw: ObjectDict = {
            "hook_event_name": "tool.execute.before",
            "tool_name": "apply_patch",
            "tool_input": {},
            "cwd": "/tmp",
            "session_id": "oc3b",
        }
        canonical = adapter.normalize_payload(raw)
        assert canonical["tool_name"] == "apply_patch", (
            "unknown or structured tool names should not be title-cased"
        )

    def test_normalize_session_idle_maps_to_stop(self) -> None:
        """session.idle → Stop."""
        adapter = OpenCodeAdapter()
        raw: ObjectDict = {
            "hook_event_name": "session.idle",
            "tool_name": "",
            "tool_input": {},
            "cwd": "/tmp",
            "session_id": "oc-test",
        }
        canonical = adapter.normalize_payload(raw)
        assert canonical["hook_event_name"] == "Stop", "session.idle not mapped to Stop"

    def test_normalize_permission_asked_maps_to_permission_request(self) -> None:
        """permission.asked → PermissionRequest."""
        adapter = OpenCodeAdapter()
        raw: ObjectDict = {
            "hook_event_name": "permission.asked",
            "tool_name": "bash",
            "tool_input": {"command": "rm -rf /"},
            "cwd": "/tmp",
            "session_id": "oc-test",
        }
        canonical = adapter.normalize_payload(raw)
        assert canonical["hook_event_name"] == "PermissionRequest", (
            "permission.asked not mapped to PermissionRequest"
        )
        assert canonical["tool_name"] == "Bash", "tool name not capitalized"

    def test_normalize_does_not_mutate_original(self) -> None:
        """normalize_payload must return a new dict, not modify the input."""
        adapter = OpenCodeAdapter()
        raw: ObjectDict = {
            "hook_event_name": "tool.execute.before",
            "tool_name": "bash",
            "tool_input": {"command": "ls"},
            "cwd": "/tmp",
            "session_id": "oc-test",
        }
        original_event = raw["hook_event_name"]
        original_tool = raw["tool_name"]
        canonical = adapter.normalize_payload(raw)
        # The returned dict should be different (shallow copy)
        assert canonical is not raw, "normalize_payload returned same dict object"
        # Original should be untouched
        assert raw["hook_event_name"] == original_event, "original event name mutated"
        assert raw["tool_name"] == original_tool, "original tool name mutated"

    def test_normalize_unknown_event_passthrough(self) -> None:
        """Unknown event names pass through unchanged (forward compat)."""
        adapter = OpenCodeAdapter()
        raw: ObjectDict = {
            "hook_event_name": "some.future.event",
            "tool_name": "",
            "tool_input": {},
            "cwd": "/tmp",
            "session_id": "oc-test",
        }
        canonical = adapter.normalize_payload(raw)
        assert canonical["hook_event_name"] == "some.future.event", (
            "unknown event name should pass through unchanged"
        )

    def test_normalize_empty_tool_name_stays_empty(self) -> None:
        """Empty string tool_name should not be capitalized to something weird."""
        adapter = OpenCodeAdapter()
        raw: ObjectDict = {
            "hook_event_name": "session.idle",
            "tool_name": "",
            "tool_input": {},
            "cwd": "/tmp",
            "session_id": "oc-test",
        }
        canonical = adapter.normalize_payload(raw)
        assert canonical["tool_name"] == "", "empty tool name should remain empty"


class TestOpenCodeAdapterNormalizeToolResult:
    """tool_result / tool_response aliasing behavior."""

    def test_normalize_tool_result_aliasing(self) -> None:
        """tool_response should be aliased to tool_result and vice versa."""
        adapter = OpenCodeAdapter()

        # Shim sends tool_result (preferred) → tool_response should appear
        raw1: ObjectDict = {
            "hook_event_name": "tool.execute.after",
            "tool_name": "bash",
            "tool_input": {"command": "echo hi"},
            "cwd": "/tmp",
            "session_id": "oc-test",
            "tool_result": "hi\n",
        }
        canonical1 = adapter.normalize_payload(raw1)
        assert canonical1["tool_result"] == "hi\n", "tool_result missing after alias"
        assert canonical1["tool_response"] == "hi\n", "tool_response alias not set"

        # Shim sends tool_response (legacy) → tool_result should appear
        raw2: ObjectDict = {
            "hook_event_name": "tool.execute.after",
            "tool_name": "bash",
            "tool_input": {"command": "echo hi"},
            "cwd": "/tmp",
            "session_id": "oc-test",
            "tool_response": "hi\n",
        }
        canonical2 = adapter.normalize_payload(raw2)
        assert canonical2["tool_result"] == "hi\n", (
            "tool_result not aliased from tool_response"
        )
        assert canonical2["tool_response"] == "hi\n", (
            "tool_response missing after alias"
        )

    def test_normalize_both_tool_result_fields_present(self) -> None:
        """When shim sends both, both pass through without double-aliasing."""
        adapter = OpenCodeAdapter()
        raw: ObjectDict = {
            "hook_event_name": "tool.execute.after",
            "tool_name": "bash",
            "tool_input": {},
            "cwd": "/tmp",
            "session_id": "oc-test",
            "tool_result": "output-a",
            "tool_response": "output-b",  # different value
        }
        canonical = adapter.normalize_payload(raw)
        # Both fields present → no aliasing, original values preserved
        assert canonical["tool_result"] == "output-a", (
            "tool_result overwritten when both present"
        )
        assert canonical["tool_response"] == "output-b", (
            "tool_response overwritten when both present"
        )

    def test_normalize_no_tool_result_fields(self) -> None:
        """PreToolUse payloads have no tool_result — shouldn't create one."""
        adapter = OpenCodeAdapter()
        raw = {
            "hook_event_name": "tool.execute.before",
            "tool_name": "bash",
            "tool_input": {"command": "ls"},
            "cwd": "/tmp",
            "session_id": "oc-test",
        }
        canonical = adapter.normalize_payload(raw)
        assert "tool_result" not in canonical, (
            "tool_result should not be created for PreToolUse"
        )
        assert "tool_response" not in canonical, (
            "tool_response should not be created for PreToolUse"
        )


class TestOpenCodeAdapterRender:
    def test_stop_block_renders_continue_action(self) -> None:
        adapter = OpenCodeAdapter()
        finding = RuleFinding(
            rule_id="STOP-001",
            title="continue",
            severity=Severity.HIGH,
            decision="block",
            message="Keep going.",
        )
        output = require_rendered(
            adapter.render_output("Stop", [finding], decision="block")
        )
        assert output == {
            "action": "continue",
            "reason": "[STOP-001 | HIGH] Keep going.",
        }
