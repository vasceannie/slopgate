/**
 * Pi Slopgate Extension
 *
 * Bridges Pi extension events to `slopgate handle --platform pi`.
 *
 * Reference: https://pi.dev/docs/latest/extensions
 */


interface NodeProcessLike {
  cwd(): string
  env: Record<string, string | undefined>
}

import { spawn } from "node:child_process"
import { existsSync } from "node:fs"
import { dirname, join } from "node:path"
import runtimeProcessValue from "node:process"
import { Box, Text } from "@earendil-works/pi-tui"

const runtimeProcess = runtimeProcessValue as NodeProcessLike

const SLOPGATE_ARGV = runtimeProcess.env.SLOPGATE_BIN ? [runtimeProcess.env.SLOPGATE_BIN] : ["__SLOPGATE_BIN__"]
const SESSION_ID = `pi-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
const SLOPGATE_EVENT_MESSAGE_TYPE = "slopgate-event"
const SLOPGATE_SYSTEM_PROMPT_HEADER = "Slopgate hook context for this turn:"
let lastSlopgateContext = ""

interface PiContentPart {
  text?: string
  type?: string
  [key: string]: unknown
}

type PiMessageContent = string | PiContentPart[]

type PiEventName =
  | "agent_end"
  | "before_agent_start"
  | "input"
  | "session_start"
  | "tool_call"
  | "tool_execution_end"
  | "tool_result"
  | "turn_end"
  | "user_bash"

interface PiEnforcerResult {
  block?: boolean
  reason?: string
  context?: string
  tool_result_patch?: PiToolResultPatch
  updated_input?: Record<string, unknown>
}

interface PiEventLike {
  type?: string
  toolName?: string
  toolCallId?: string
  input?: Record<string, unknown>
  args?: Record<string, unknown>
  arguments?: Record<string, unknown>
  content?: unknown
  details?: unknown
  isError?: boolean
  prompt?: string
  text?: string
  images?: unknown[]
  message?: unknown
  messages?: unknown[]
  result?: unknown
  reason?: string
  systemPrompt?: string
  command?: string
  cwd?: string
  excludeFromContext?: boolean
}

interface PiUiLike {
  editor?(title: string, prefill?: string): Promise<string | undefined>
  notify?(message: string, level?: "info" | "warning" | "error"): void
}

interface PiContextLike {
  hasUI?: boolean
  cwd?: string
  ui?: PiUiLike
}

interface PiCommandContextLike extends PiContextLike {
  ui?: PiUiLike
}

interface PiToolResultPatch {
  details?: Record<string, unknown>
  isError?: boolean
}

interface PiHookResult {
  action?: "continue" | "handled" | "transform"
  block?: boolean
  details?: unknown
  isError?: boolean
  message?: Record<string, unknown>
  reason?: string
  result?: unknown
  systemPrompt?: string
  text?: string
}

interface PiInputTransformResult {
  action: "transform"
  text: string
}

interface PiBeforeAgentStartResult {
  message?: {
    customType: string
    content: PiMessageContent
    display: boolean
    details?: Record<string, unknown>
  }
  systemPrompt?: string
}

type PiEventHandler = (
  event: PiEventLike,
  ctx: PiContextLike,
) => Promise<PiHookResult | void> | PiHookResult | void

type PiCommandHandler = (
  args: string,
  ctx: PiCommandContextLike,
) => Promise<void>

interface PiMessageRenderOptions {
  expanded: boolean
}

interface PiExtensionAPI {
  on(eventName: PiEventName, handler: PiEventHandler): void
  registerCommand(
    name: string,
    options: {
      description: string
      handler: PiCommandHandler
    },
  ): void
  registerMessageRenderer(
    customType: string,
    renderer: (
      message: {
        customType: string
        content: PiMessageContent
        details?: Record<string, unknown>
      },
      options: PiMessageRenderOptions,
      theme: {
        bg(name: string, text: string): string
        fg(name: string, text: string): string
        bold(text: string): string
      },
    ) => unknown,
  ): void
  sendMessage<T = unknown>(
    message: {
      customType: string
      content: PiMessageContent
      display: boolean
      details?: T
    },
    options?: {
      triggerTurn?: boolean
      deliverAs?: "steer" | "followUp" | "nextTurn"
    },
  ): void
}

function findManagedRepoRoot(start: string): string | null {
  let current = start
  while (true) {
    if (existsSync(join(current, "slopgate.toml"))) {
      return current
    }
    const parent = dirname(current)
    if (parent === current) {
      return null
    }
    current = parent
  }
}

function cwdFromContext(ctx: PiContextLike): string {
  return typeof ctx.cwd === "string" && ctx.cwd.trim() ? ctx.cwd : runtimeProcess.cwd()
}

function applyUpdatedInput(
  event: PiEventLike,
  updatedInput: Record<string, unknown> | undefined,
): void {
  if (!updatedInput || !event.input) {
    return
  }
  Object.assign(event.input, updatedInput)
}

function toolInputFromEvent(event: PiEventLike): Record<string, unknown> {
  if (typeof event.command === "string") {
    return {
      command: event.command,
      exclude_from_context: event.excludeFromContext === true,
    }
  }
  return event.input || event.args || event.arguments || {}
}

function promptFromEvent(event: PiEventLike): string {
  return event.text || event.prompt || ""
}

function textFromContentPart(part: unknown): string {
  if (typeof part === "string") {
    return part
  }
  if (!part || typeof part !== "object") {
    return ""
  }
  const text = (part as { text?: unknown }).text
  return typeof text === "string" ? text : ""
}

function toolResultFromEvent(event: PiEventLike): unknown {
  if (Array.isArray(event.content)) {
    return {
      stdout: event.content.map(textFromContentPart).filter(Boolean).join("\n"),
      details: event.details,
      is_error: event.isError === true,
      content: event.content,
    }
  }
  return event.content ?? event.result ?? event.message ?? null
}

function inputTransformFromUpdatedInput(
  updatedInput: Record<string, unknown> | undefined,
): PiInputTransformResult | null {
  if (!updatedInput) {
    return null
  }
  const text = updatedInput.text ?? updatedInput.prompt
  if (typeof text !== "string") {
    return null
  }
  const result: PiInputTransformResult = { action: "transform", text }
  return result
}

function appendSlopgateSystemPrompt(
  systemPrompt: string | undefined,
  context: string,
): string {
  const slopgateContext = `${SLOPGATE_SYSTEM_PROMPT_HEADER}\n${context}`.trim()
  const basePrompt = systemPrompt?.trim()
  return basePrompt ? `${basePrompt}\n\n${slopgateContext}` : slopgateContext
}

function beforeAgentStartResult(
  event: PiEventLike,
  result: PiEnforcerResult | null,
): PiBeforeAgentStartResult | void {
  if (!result?.context) {
    return
  }
  lastSlopgateContext = result.context
  return {
    message: {
      customType: SLOPGATE_EVENT_MESSAGE_TYPE,
      content: chatMessageContent("context", "before_agent_start", result),
      display: true,
      details: slopgateMessageDetails("context", "before_agent_start", result),
    },
    systemPrompt: appendSlopgateSystemPrompt(event.systemPrompt, result.context),
  }
}

function compactSlopgateLines(result: PiEnforcerResult): string[] {
  const lines = ["slopgate"]
  const message = result.reason || result.context
  if (message) {
    const compact = message.split("\n").map((line) => line.trim()).filter(Boolean).slice(0, 4)
    lines.push(...compact)
  }
  return lines
}

function slopgateMessageDetails(
  state: "blocked" | "context" | "warning",
  eventName: string,
  result: PiEnforcerResult,
): Record<string, unknown> {
  return {
    state,
    event: eventName,
    reason: result.reason,
    context: result.context,
    summary: chatMessageContent(state, eventName, result),
  }
}

function chatMessageContent(
  state: "blocked" | "context" | "warning",
  eventName: string,
  result: PiEnforcerResult,
): string {
  if (state === "context") {
    return "Context added to this turn. Run /slopgate-context for details."
  }
  const compact = compactSlopgateLines(result).slice(1)
  return compact.length > 0 ? compact.join("\n") : `Slopgate ${state} at ${eventName}`
}

function stringDetail(details: Record<string, unknown> | undefined, key: string): string {
  const value = details?.[key]
  return typeof value === "string" ? value : ""
}

function renderSlopgateMessage(
  message: {
    customType: string
    content: PiMessageContent
    details?: Record<string, unknown>
  },
  _options: PiMessageRenderOptions,
  theme: {
    bg(name: string, text: string): string
    fg(name: string, text: string): string
    bold(text: string): string
  },
): unknown {
  const state = stringDetail(message.details, "state")
  const summary = stringDetail(message.details, "summary") || "Slopgate context captured."
  const label = state === "blocked" ? "blocked" : state === "warning" ? "warning" : "context"
  const color = state === "blocked" ? "error" : state === "warning" ? "warning" : "accent"
  const title = `${theme.bold(theme.fg(color, "Slopgate"))} ${theme.fg("muted", label)}`
  const lines = [title, summary]
  const box = new Box(1, 1, (text) => theme.bg("customMessageBg", text))
  box.addChild(new Text(lines.join("\n"), 0, 0))
  return box
}

function registerSlopgateMessageRenderer(pi: PiExtensionAPI): void {
  pi.registerMessageRenderer(SLOPGATE_EVENT_MESSAGE_TYPE, renderSlopgateMessage)
}

function registerSlopgateContextCommand(pi: PiExtensionAPI): void {
  pi.registerCommand("slopgate-context", {
    description: "Show the latest Slopgate context injected into the current session.",
    async handler(_args: string, ctx: PiCommandContextLike): Promise<void> {
      if (!lastSlopgateContext) {
        ctx.ui?.notify?.("No Slopgate context has been captured yet.", "info")
        return
      }
      if (ctx.ui?.editor) {
        await ctx.ui.editor("Slopgate context", lastSlopgateContext)
        return
      }
      ctx.ui?.notify?.("Slopgate context is available after the next TUI turn.", "info")
    },
  })
}

function clearSlopgateContext(): void {
  lastSlopgateContext = ""
}

function sendSlopgateChatMessage(
  pi: PiExtensionAPI,
  result: PiEnforcerResult | null,
  eventName: string,
  state: "blocked" | "context" | "warning",
): void {
  if (!result) {
    return
  }
  pi.sendMessage(
    {
      customType: SLOPGATE_EVENT_MESSAGE_TYPE,
      content: chatMessageContent(state, eventName, result),
      display: true,
      details: slopgateMessageDetails(state, eventName, result),
    },
    { triggerTurn: false },
  )
}

function advisory(pi: PiExtensionAPI, eventName: string, result: PiEnforcerResult | null): void {
  if (!result) {
    return
  }
  const state = result.reason ? "warning" : "context"
  sendSlopgateChatMessage(pi, result, eventName, state)
}

function mergeToolResultPatch(
  event: PiEventLike,
  result: PiEnforcerResult | null,
): PiToolResultPatch | void {
  const patch = result?.tool_result_patch
  if (!patch) {
    return
  }
  const merged: PiToolResultPatch = {}
  if ("isError" in patch) {
    merged.isError = patch.isError
  }
  if (patch.details) {
    const existingDetails = event.details && typeof event.details === "object" && !Array.isArray(event.details)
      ? event.details as Record<string, unknown>
      : {}
    merged.details = { ...existingDetails, ...patch.details }
  }
  return merged
}

function chunkToUtf8(chunk: string | Uint8Array): string {
  if (typeof chunk === "string") {
    return chunk
  }
  return new TextDecoder().decode(chunk)
}

function enforcerPayload(
  eventName: string,
  event: PiEventLike,
  ctx: PiContextLike,
): Record<string, unknown> {
  const cwd = cwdFromContext(ctx)
  return {
    hook_event_name: eventName,
    tool_name: event.toolName || (typeof event.command === "string" ? "bash" : ""),
    tool_call_id: event.toolCallId || "",
    tool_input: toolInputFromEvent(event),
    cwd,
    session_id: SESSION_ID,
    transcript_path: null,
    prompt: promptFromEvent(event),
    tool_result: toolResultFromEvent(event),
    tool_response: toolResultFromEvent(event),
    pi_event: event,
  }
}

function callEnforcer(
  payload: Record<string, unknown>,
  managedRepo: boolean,
): Promise<PiEnforcerResult | null> {
  return new Promise((resolve) => {
    const cwd = typeof payload.cwd === "string" ? payload.cwd : runtimeProcess.cwd()
    const proc = spawn(
      SLOPGATE_ARGV[0],
      [...SLOPGATE_ARGV.slice(1), "handle", "--platform", "pi"],
      {
        cwd,
        env: runtimeProcess.env,
        stdio: ["pipe", "pipe", "pipe"],
      },
    )
    let stdout = ""
    let stderr = ""
    proc.stdout.on("data", (chunk: string | Uint8Array) => {
      stdout += chunkToUtf8(chunk)
    })
    proc.stderr.on("data", (chunk: string | Uint8Array) => {
      stderr += chunkToUtf8(chunk)
    })
    proc.on("error", (error: Error) => {
      console.error(`[slopgate] enforcer failed: ${error.message}`)
      resolve(
        managedRepo
          ? {
              block: true,
              reason: "slopgate degraded mode: enforcer subprocess failed in managed repo.",
            }
          : null,
      )
    })
    proc.on("close", (code: number | null) => {
      if (code !== 0) {
        console.error(`[slopgate] exit ${code}: ${stderr}`)
        resolve(
          managedRepo
            ? {
                block: true,
                reason: "slopgate degraded mode: enforcer subprocess failed in managed repo.",
              }
            : null,
        )
        return
      }
      const trimmed = stdout.trim()
      if (!trimmed) {
        resolve(null)
        return
      }
      try {
        resolve(JSON.parse(trimmed) as PiEnforcerResult)
      } catch (error) {
        console.error(`[slopgate] invalid enforcer JSON: ${error}`)
        resolve(
          managedRepo
            ? {
                block: true,
                reason: "slopgate degraded mode: enforcer returned invalid JSON.",
              }
            : null,
        )
      }
    })
    proc.stdin.write(JSON.stringify(payload))
    proc.stdin.end()
  })
}

async function enforce(
  eventName: string,
  event: PiEventLike,
  ctx: PiContextLike,
): Promise<PiEnforcerResult | null> {
  const cwd = cwdFromContext(ctx)
  return callEnforcer(enforcerPayload(eventName, event, ctx), findManagedRepoRoot(cwd) !== null)
}

export default function slopgatePiExtension(pi: PiExtensionAPI) {
  registerSlopgateMessageRenderer(pi)
  registerSlopgateContextCommand(pi)

  pi.on("session_start", () => {
    clearSlopgateContext()
  })

  pi.on("tool_call", async (event, ctx) => {
    const result = await enforce("tool_call", event, ctx)
    applyUpdatedInput(event, result?.updated_input)
    if (result?.block) {
      sendSlopgateChatMessage(pi, result, "tool_call", "blocked")
      return { block: true, reason: result.reason || "Blocked by slopgate" }
    }
    advisory(pi, "tool_call", result)
  })

  pi.on("tool_result", async (event, ctx) => {
    const result = await enforce("tool_result", event, ctx)
    advisory(pi, "tool_result", result)
    return mergeToolResultPatch(event, result)
  })

  pi.on("tool_execution_end", async (event, ctx) => {
    const result = await enforce("tool_execution_end", event, ctx)
    advisory(pi, "tool_execution_end", result)
  })

  pi.on("input", async (event, ctx) => {
    const result = await enforce("input", event, ctx)
    if (result?.block) {
      sendSlopgateChatMessage(pi, result, "input", "blocked")
      if (result.reason && ctx.ui?.notify) {
        ctx.ui.notify(result.reason, "warning")
      }
      return { action: "handled" }
    }
    const transform = inputTransformFromUpdatedInput(result?.updated_input)
    if (transform) {
      return transform
    }
    advisory(pi, "input", result)
  })

  pi.on("before_agent_start", async (event, ctx) => {
    const result = await enforce("before_agent_start", event, ctx)
    const response = beforeAgentStartResult(event, result)
    if (!response) {
      advisory(pi, "before_agent_start", result)
    }
    return response
  })

  pi.on("turn_end", async (event, ctx) => {
    advisory(pi, "turn_end", await enforce("turn_end", event, ctx))
  })

  pi.on("agent_end", async (event, ctx) => {
    advisory(pi, "agent_end", await enforce("agent_end", event, ctx))
  })

  pi.on("user_bash", async (event, ctx) => {
    const result = await enforce("user_bash", event, ctx)
    if (result?.block) {
      sendSlopgateChatMessage(pi, result, "user_bash", "blocked")
      return {
        result: {
          output: result.reason || "Blocked by slopgate",
          exitCode: 1,
          cancelled: false,
          truncated: false,
        },
      }
    }
    advisory(pi, "user_bash", result)
  })
}
