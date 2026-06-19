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
const SLOPGATE_GUARD_MESSAGE = "Violations flagged by slopgate must be fixed, not disabled, bypassed, or argued as preexisting. Do not modify or delete slopgate configuration files, extension files, or rule definitions. Fix the flagged issue directly."

const SLOPGATE_PROTECTED_PATHS = new Set([
  "slopgate.toml",
  ".pi/extensions/pi-slopgate",
  ".pi/agent/extensions/pi-slopgate",
  "pi-slopgate/index.ts",
  "pi_extension.ts",
])

const SLOPGATE_PROTECTED_SEGMENTS = [
  "slopgate/src/slopgate/rules",
  "slopgate/src/slopgate/adapters",
]

function isSlopgatePath(target: string): boolean {
  const normalized = target.replace(/\\/g, "/")
  // Direct filename match
  const fileName = normalized.split("/").pop() || ""
  if (SLOPGATE_PROTECTED_PATHS.has(fileName)) {
    return true
  }
  // Full path segment match
  if (SLOPGATE_PROTECTED_PATHS.has(normalized)) {
    return true
  }
  // Path contains a protected segment
  for (const segment of SLOPGATE_PROTECTED_SEGMENTS) {
    if (normalized.includes(segment)) {
      return true
    }
  }
  return false
}
let lastSlopgateContext = ""
let lastStopGuidance = ""

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
  return event.input || event.args || {}
}

function toolPathFromEvent(event: PiEventLike): string | undefined {
  const input = toolInputFromEvent(event)
  const path = input.path || input.file || input.filePath || input.file_path
  return typeof path === "string" ? path : undefined
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
  // tool_execution_end may have details/result without a content array
  if (event.details != null || event.isError != null) {
    const details = event.details as Record<string, unknown> | undefined
    const exitCode = details?.exitCode ?? details?.exit_code ?? null
    return {
      stdout: typeof event.content === "string" ? event.content :
              typeof event.result === "string" ? event.result :
              event.result != null ? JSON.stringify(event.result) : "",
      details: event.details,
      is_error: event.isError === true,
      exit_code: exitCode,
    }
  }
  return event.content ?? event.result ?? null
}

function messageToText(msg: unknown): string {
  if (typeof msg === "string") return msg
  if (Array.isArray(msg)) {
    return msg.map(textFromContentPart).filter(Boolean).join("\n")
  }
  if (msg && typeof msg === "object") {
    const content = (msg as { content?: unknown }).content
    if (content != null) return messageToText(content)
    const text = (msg as { text?: unknown }).text
    if (typeof text === "string") return text
  }
  return ""
}

function stopResponseFromEvent(event: PiEventLike): string {
  // Try the last assistant message first (agent_end provides event.message)
  if (event.message != null) {
    return messageToText(event.message)
  }
  // Fall back to the last message in messages array
  if (Array.isArray(event.messages) && event.messages.length > 0) {
    const lastMsg = event.messages[event.messages.length - 1]
    if (lastMsg && typeof lastMsg === "object") {
      const content = (lastMsg as { content?: unknown }).content
      if (content != null) return messageToText(content)
    }
  }
  // Final fallback: stop reason
  if (typeof event.reason === "string") {
    return event.reason
  }
  return ""
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
  const slopgateBlock = `${SLOPGATE_SYSTEM_PROMPT_HEADER}\n${context}\n\n${SLOPGATE_GUARD_MESSAGE}`.trim()
  const basePrompt = systemPrompt?.trim()
  return basePrompt ? `${basePrompt}\n\n${slopgateBlock}` : slopgateBlock
}

function beforeAgentStartResult(
  event: PiEventLike,
  result: PiEnforcerResult | null,
: PiBeforeAgentStartResult | void {
  const hasContext: boolean = !!result?.context
  const guidance: string = lastStopGuidance
  if (!hasContext && !guidance) {
    return
  }
  if (hasContext) {
    lastSlopgateContext = result!.context!
  }
  // Build system prompt from hook context + stop guidance
  let promptContext = ""
  if (hasContext) promptContext += result!.context
  if (guidance) {
    if (promptContext) promptContext += "\n\n"
    promptContext += guidance
  }
  lastStopGuidance = ""

  const response: PiBeforeAgentStartResult = {
    systemPrompt: appendSlopgateSystemPrompt(event.systemPrompt, promptContext),
  }
  if (hasContext) {
    response.message = {
      customType: SLOPGATE_EVENT_MESSAGE_TYPE,
      content: chatMessageContent("context", "before_agent_start", result!),
      display: true,
      details: slopgateMessageDetails("context", "before_agent_start", result!),
    }
  }
  return response
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
: unknown {
  const state: string = stringDetail(message.details, "state")
  const eventName: string = stringDetail(message.details, "event")
  const reason: string = stringDetail(message.details, "reason")
  const summary: string = stringDetail(message.details, "summary") || "Slopgate context captured."

  const label: string = state === "blocked" ? "blocked" : state === "warning" ? "warning" : "context"
  const color: string = state === "blocked" ? "error" : state === "warning" ? "warning" : "accent"

  // Title: Slopgate · event_name  label
  const eventPart: string = eventName ? ` ${theme.fg("dim", `· ${eventName}`)}` : ""
  const title: string = `${theme.bold(theme.fg(color, "Slopgate"))}${eventPart} ${theme.fg("muted", label)}`

  const lines: string[] = [title]

  // Expanded: show full reason and metadata
  if (_options.expanded && reason) {
    lines.push("", theme.fg("dim", reason))
  } else {
    lines.push(summary)
  }

  const box = new Box(1, 1, (text: string) => theme.bg("customMessageBg", text))
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
  lastStopGuidance = ""
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
  // Only surface guidance (reason) as a chat message.
  // Context is already in the system prompt via before_agent_start.
  if (!result?.reason) {
    return
  }
  sendSlopgateChatMessage(pi, result, eventName, "warning")
}

function mergeToolResultPatch(
  event: PiEventLike,
  result: PiEnforcerResult | null,
: PiToolResultPatch | void {
  if (!result) {
    return
  }
  const patch: Record<string, unknown> | undefined = result.tool_result_patch
  const merged: PiToolResultPatch = {}
  if (patch && "isError" in patch) {
    merged.isError = patch.isError
  }
  if (patch?.details) {
    const existingDetails = event.details && typeof event.details === "object" && !Array.isArray(event.details)
      ? event.details as Record<string, unknown>
      : {}
    merged.details = { ...existingDetails, ...patch.details }
  }
  // Inject guidance (reason) inline so the model sees it immediately
  // rather than waiting for the next turn's chat message.
  if (result.reason) {
    const existingDetails = event.details && typeof event.details === "object" && !Array.isArray(event.details)
      ? event.details as Record<string, unknown>
      : {}
    merged.details = { ...(merged.details ?? existingDetails), slopgate_guidance: result.reason }
  }
  if (Object.keys(merged).length === 0) {
    return
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

  // Map tool_execution_end with non-zero exit to PostToolUseFailure
  let hookEventName = eventName
  if (eventName === "tool_execution_end" && event.isError === true) {
    hookEventName = "PostToolUseFailure"
  }

  // Build stop_response for agent_end / turn_end so STOP-001/STOP-002 can inspect it
  let stopResponse = ""
  if (eventName === "agent_end" || eventName === "turn_end") {
    stopResponse = stopResponseFromEvent(event)
  }

  // Detect interrupt / cancellation from details
  const details = event.details as Record<string, unknown> | undefined
  const isInterrupt = details?.cancelled === true || details?.interrupted === true || false

  return {
    hook_event_name: hookEventName,
    tool_name: event.toolName || (typeof event.command === "string" ? "bash" : ""),
    tool_call_id: event.toolCallId || "",
    tool_input: toolInputFromEvent(event),
    cwd,
    session_id: SESSION_ID,
    transcript_path: null,
    prompt: promptFromEvent(event),
    tool_result: toolResultFromEvent(event),
    tool_response: toolResultFromEvent(event),
    stop_response: stopResponse || undefined,
    is_interrupt: isInterrupt || undefined,
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
    // Block write/edit/delete operations on slopgate-owned files
    const toolName = event.toolName || ""
    if (toolName === "write" || toolName === "edit" || toolName === "replace" || toolName === "bash") {
      const toolPath = toolPathFromEvent(event)
      if (toolPath && isSlopgatePath(toolPath)) {
        const cwd = cwdFromContext(ctx)
        if (findManagedRepoRoot(cwd)) {
          return {
            block: true,
            reason: `Cannot modify slopgate infrastructure: ${toolPath}. Fix the flagged issue instead.`,
          }
        }
      }
    }

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
    const result = await enforce("turn_end", event, ctx)
    if (result?.reason) {
      lastStopGuidance = result.reason
    }
  })

  pi.on("agent_end", async (event, ctx) => {
    const result = await enforce("agent_end", event, ctx)
    if (result?.reason) {
      lastStopGuidance = result.reason
    }
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
