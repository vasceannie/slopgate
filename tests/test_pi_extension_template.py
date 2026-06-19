from __future__ import annotations

import json
import sys
from collections.abc import Sequence

import slopgate.installer._pi


def pi_extension_template() -> str:
    from slopgate.resources import resource_path

    return resource_path("pi_extension.ts").read_text(encoding="utf-8")


def contains_markers(source: str, markers: Sequence[str], contract: str) -> bool:
    missing = [marker for marker in markers if marker not in source]
    assert not missing, f"{contract}: missing markers {missing!r}"
    return True


def excludes_markers(source: str, markers: Sequence[str], contract: str) -> bool:
    present = [marker for marker in markers if marker in source]
    assert not present, f"{contract}: unexpected markers {present!r}"
    return True


def test_pi_extension_falls_back_to_python_module_invocation() -> None:
    extension = slopgate.installer._pi.render_pi_extension(
        pi_extension_template(), sys.executable
    )
    assert contains_markers(
        extension,
        [json.dumps([sys.executable, "-m", "slopgate"])],
        "python fallback argv is rendered",
    )
    assert excludes_markers(
        extension,
        ["__SLOPGATE_BIN__", f'{json.dumps(sys.executable)}, "handle"'],
        "python fallback argv avoids invalid direct handle invocation",
    )


def test_pi_extension_uses_documented_input_handled_action() -> None:
    extension = pi_extension_template()
    assert contains_markers(
        extension,
        ['{ action: "handled" }', 'ctx.ui.notify(result.reason, "warning")'],
        "blocked input uses documented handled action",
    )
    assert excludes_markers(
        extension,
        ['"warn"', "{ handled: true }"],
        "blocked input avoids undocumented action shapes",
    )


def test_pi_extension_uses_documented_input_event_text() -> None:
    assert contains_markers(
        pi_extension_template(),
        [
            "text?: string",
            "function promptFromEvent(event: PiEventLike): string",
            'return event.text || event.prompt || ""',
            "prompt: promptFromEvent(event)",
        ],
        "input prompt text is sourced from documented event text",
    )


def test_pi_extension_supports_documented_input_transform_result() -> None:
    assert contains_markers(
        pi_extension_template(),
        [
            'action?: "continue" | "handled" | "transform"',
            'return { action: "handled" }',
            'action: "transform", text',
            "inputTransformFromUpdatedInput(result?.updated_input)",
        ],
        "input transforms use documented action result",
    )


def test_pi_extension_maps_tool_args_and_results_from_pi_events() -> None:
    assert contains_markers(
        pi_extension_template(),
        [
            "args?: Record<string, unknown>",
            "result?: unknown",
            "return event.input || event.args || {}",
            "function textFromContentPart(part: unknown): string",
            'stdout: event.content.map(textFromContentPart).filter(Boolean).join("\\n")',
            "return event.content ?? event.result ?? null",
            "tool_input: toolInputFromEvent(event)",
            "tool_result: toolResultFromEvent(event)",
            "tool_response: toolResultFromEvent(event)",
        ],
        "tool payload mapping preserves Pi args and result content",
    )


def test_pi_extension_maps_user_bash_commands_to_bash_tool_input() -> None:
    assert contains_markers(
        pi_extension_template(),
        [
            '| "user_bash"',
            'pi.on("user_bash"',
            'typeof event.command === "string"',
            'tool_name: event.toolName || (typeof event.command === "string" ? "bash" : "")',
            "exclude_from_context: event.excludeFromContext === true",
            "exitCode: 1",
        ],
        "user_bash is normalized as bash tool input",
    )


def test_pi_extension_delivers_context_through_message_channel() -> None:
    extension = pi_extension_template()
    assert contains_markers(
        extension,
        [
            "function beforeAgentStartResult(",
            'content: chatMessageContent("context", "before_agent_start", result!),',
            "display: true,",
            'details: slopgateMessageDetails("context", "before_agent_start", result!),',
            "lastSlopgateContext = result",
            "const response = beforeAgentStartResult(event, result)",
            'const SLOPGATE_SYSTEM_PROMPT_HEADER = "Slopgate hook context for this turn:"',
            "function appendSlopgateSystemPrompt(",
            "systemPrompt: appendSlopgateSystemPrompt(event.systemPrompt, promptContext),",
        ],
        "before_agent_start delivers context and stop guidance via system prompt and message channel",
    )
    assert excludes_markers(
        extension,
        [
            "SLOPGATE_CONTEXT_MESSAGE_TYPE",
        ],
        "before_agent_start avoids legacy context message type",
    )


def test_pi_extension_surfaces_context_status_without_hiding_context() -> None:
    extension = pi_extension_template()
    assert contains_markers(
        extension,
        [
            'const SLOPGATE_EVENT_MESSAGE_TYPE = "slopgate-event"',
            "type PiMessageContent = string | PiContentPart[]",
            "customType: SLOPGATE_EVENT_MESSAGE_TYPE",
            'content: chatMessageContent("context", "before_agent_start", result!)',
            "display: true",
            'slopgateMessageDetails("context", "before_agent_start", result!)',
            "lastSlopgateContext = result",
            'pi.on("session_start", () => {',
            "clearSlopgateContext()",
            '"Context added to this turn. Run /slopgate-context for details."',
        ],
        "before_agent_start keeps compact visible status while storing full context",
    )
    assert excludes_markers(
        extension,
        [
            'sendSlopgateChatMessage(pi, result, "before_agent_start", "context")',
            "Expand for details",
            "return `${heading} · ${eventName}\\nContext captured in details.`",
            "content: result.context",
        ],
        "before_agent_start avoids context-only rendering paths",
    )


def test_pi_extension_does_not_require_node_buffer_global() -> None:
    assert excludes_markers(
        pi_extension_template(),
        ["Buffer"],
        "extension does not require Node Buffer global",
    )


def test_pi_extension_imports_node_and_tui_without_suppressions_or_require() -> None:
    extension = pi_extension_template()
    assert contains_markers(
        extension,
        [
            'from "@earendil-works/pi-tui"',
            'from "node:child_process"',
            'from "node:fs"',
            'from "node:path"',
            'from "node:process"',
            "interface PiExtensionAPI",
            "async (event, ctx)",
        ],
        "extension uses typed ESM imports and local Pi API declarations",
    )
    assert excludes_markers(
        extension,
        [
            "@earendil-works/pi-coding-agent",
            "@ts-ignore",
            "@ts-expect-error",
            "runtimeRequire",
            "require(",
            'eval)("require")',
            "require is not defined",
        ],
        "extension avoids suppressions and require fallbacks",
    )


def test_pi_extension_keeps_post_tool_findings_advisory() -> None:
    extension = pi_extension_template()
    assert contains_markers(
        extension,
        [
            'pi.on("tool_result"',
            'pi.on("tool_execution_end"',
            "return mergeToolResultPatch(event, result)",
            "tool_result_patch?: PiToolResultPatch",
        ],
        "post-tool events stay advisory and patch result metadata",
    )
    assert excludes_markers(
        extension, ["throw new Error"], "post-tool events do not throw"
    )


def test_pi_extension_surfaces_slopgate_activity_as_chat_messages() -> None:
    extension = pi_extension_template()
    assert contains_markers(
        extension,
        [
            "sendMessage<T = unknown>(",
            "content: PiMessageContent",
            "registerMessageRenderer(",
            "function renderSlopgateMessage(",
            "bg(name: string, text: string): string",
            'const box = new Box(1, 1, (text: string) => theme.bg("customMessageBg", text))',
            'const title = `${theme.bold(theme.fg(color, "Slopgate"))}',
            'const summary = stringDetail(message.details, "summary") || "Slopgate context captured."',
            "const lines = [title]",
            'box.addChild(new Text(lines.join("\\n"), 0, 0))',
            "return box",
            "pi.registerMessageRenderer(SLOPGATE_EVENT_MESSAGE_TYPE, renderSlopgateMessage)",
            "function sendSlopgateChatMessage(",
            "customType: SLOPGATE_EVENT_MESSAGE_TYPE",
            "display: true",
            "{ triggerTurn: false }",
            'sendSlopgateChatMessage(pi, result, "tool_call", "blocked")',
            'sendSlopgateChatMessage(pi, result, "user_bash", "blocked")',
        ],
        "Slopgate activity uses one custom chat renderer and visible messages",
    )
    assert excludes_markers(
        extension,
        [
            'lines.push(theme.fg("dim", event))',
            "setStatus",
            "setWidget",
        ],
        "chat renderer avoids footer/widget fallbacks",
    )


def test_pi_extension_uses_command_for_full_context_details() -> None:
    extension = pi_extension_template()
    assert contains_markers(
        extension,
        [
            'stringDetail(message.details, "summary")',
            "summary: chatMessageContent(state, eventName, result)",
            "registerCommand(",
            'pi.registerCommand("slopgate-context"',
            "Show the latest Slopgate context injected into the current session.",
            'await ctx.ui.editor("Slopgate context", lastSlopgateContext)',
            "No Slopgate context has been captured yet.",
        ],
        "full context details are exposed through a documented command editor",
    )
    assert excludes_markers(
        extension,
        ["JSON.stringify(message.details"],
        "context details are not dumped as raw JSON in chat",
    )


def test_pi_extension_context_advisory_uses_compact_component_state() -> None:
    extension = pi_extension_template()
    assert contains_markers(
        extension,
        [
            'if (!result?.reason) {',
            'sendSlopgateChatMessage(pi, result, eventName, "warning")',
        ],
        "advisory only sends chat for guidance (reason), not context-only",
    )
    assert excludes_markers(
        extension,
        ['const state = result.reason ? "warning" : "context"',
         'eventName, "context")'],
        "advisory no longer sends context-only chat messages",
    )
