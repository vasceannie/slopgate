/**
 * OMP Slopgate Extension
 *
 * Bridges OMP extension events to `slopgate handle --platform omp`.
 */

import { spawn } from "node:child_process"
import { existsSync } from "node:fs"
import { dirname, join, resolve as resolvePath } from "node:path"
import process from "node:process"

import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent"
import type { ExtensionContext } from "@oh-my-pi/pi-coding-agent"
import { Box, Text } from "@oh-my-pi/pi-tui"

type JsonRecord = Record<string, unknown>

type ToolResultPatch = {
  readonly details?: JsonRecord
  readonly isError?: boolean
}

type EnforcerResult = {
  readonly additionalContext?: string
  readonly block?: boolean
  readonly context?: string
  readonly continue?: boolean
  readonly handled?: boolean
  readonly reason?: string
  readonly text?: string
  readonly toolResultPatch?: ToolResultPatch
  readonly updatedInput?: JsonRecord
}

const SLOPGATE_ARGV = process.env.SLOPGATE_BIN ? [process.env.SLOPGATE_BIN] : ["__SLOPGATE_BIN__"]
const MESSAGE_TYPE = "slopgate-event"
const MAX_STOP_CONTINUATIONS = 8
const CAP_NOTICE = "slopgate: continuation cap reached (8); fix remaining findings manually."
const PROMPT_HEADER = "Slopgate hook context for this turn:"
const GUARD_MESSAGE = "Fix Slopgate findings directly; do not disable or bypass its rules."
const PROTECTED_NAMES = new Set([
  "slopgate.toml",
  "omp_extension.ts",
  ".omp/extensions/omp-slopgate",
  ".omp/agent/extensions/omp-slopgate",
  "omp-slopgate/index.ts",
])
const PROTECTED_SEGMENTS = [
  "slopgate/src/slopgate/rules",
  "slopgate/src/slopgate/adapters",
  ".omp/extensions/omp-slopgate",
  ".omp/agent/extensions/omp-slopgate",
]

let lastSlopgateContext = ""
let lastStopGuidance = ""
const stopContinuationCounts = new Map<string, number>()

function isRecord(value: unknown): value is JsonRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function stringValue(record: JsonRecord, key: string): string | undefined {
  const value = record[key]
  return typeof value === "string" ? value : undefined
}

function booleanValue(record: JsonRecord, key: string): boolean | undefined {
  const value = record[key]
  return typeof value === "boolean" ? value : undefined
}

function recordValue(record: JsonRecord, key: string): JsonRecord | undefined {
  const value = record[key]
  return isRecord(value) ? value : undefined
}

function parseEnforcerResult(value: unknown): EnforcerResult | null {
  if (!isRecord(value)) return null
  const patch = recordValue(value, "tool_result_patch")
  return {
    additionalContext: stringValue(value, "additionalContext"),
    block: booleanValue(value, "block"),
    context: stringValue(value, "context"),
    continue: booleanValue(value, "continue"),
    handled: booleanValue(value, "handled"),
    reason: stringValue(value, "reason"),
    text: stringValue(value, "text"),
    toolResultPatch: patch
      ? { details: recordValue(patch, "details"), isError: booleanValue(patch, "isError") }
      : undefined,
    updatedInput: recordValue(value, "updated_input"),
  }
}

function findManagedRepoRoot(start: string): string | null {
  let current = resolvePath(start)
  while (true) {
    if (existsSync(join(current, "slopgate.toml"))) return current
    const parent = dirname(current)
    if (parent === current) return null
    current = parent
  }
}

function currentSessionId(ctx: ExtensionContext): string {
  return process.env.SLOPGATE_SESSION_ID || ctx.sessionManager.getSessionId()
}

function resetStopContinuationCount(sessionId: string): void {
  stopContinuationCounts.delete(sessionId)
}

function extractSessionStopResponse(message: unknown): string {
  if (!isRecord(message)) return ""
  const content = message.content
  if (typeof content === "string") return content
  if (!Array.isArray(content)) return ""
  const textParts: string[] = []
  for (const part of content) {
    if (isRecord(part) && part.type === "text" && typeof part.text === "string") textParts.push(part.text)
  }
  return textParts.join("\n")
}

function eventInput(event: unknown): JsonRecord {
  if (!isRecord(event)) return {}
  const input = recordValue(event, "input")
  if (input) return input
  const command = stringValue(event, "command")
  if (command) return { command, exclude_from_context: event.excludeFromContext === true }
  const code = stringValue(event, "code")
  return code ? { code, exclude_from_context: event.excludeFromContext === true } : {}
}

function enforcerPayload(
  eventName: string,
  event: unknown,
  ctx: ExtensionContext,
  extra: JsonRecord = {},
): JsonRecord {
  const raw = isRecord(event) ? event : {}
  const toolName = stringValue(raw, "toolName")
    || (eventName === "user_bash" ? "bash" : eventName === "user_python" ? "python" : "")
  return {
    ...raw,
    hook_event_name: eventName,
    tool_name: toolName,
    tool_call_id: stringValue(raw, "toolCallId") || "",
    tool_input: eventInput(event),
    tool_result: raw.content ?? raw.result ?? null,
    tool_response: raw.content ?? raw.result ?? null,
    cwd: ctx.cwd,
    session_id: currentSessionId(ctx),
    transcript_path: null,
    prompt: stringValue(raw, "text") || "",
    omp_event: event,
    ...extra,
  }
}

function failedEnforcerResult(managedRepo: boolean, reason: string): EnforcerResult | null {
  return managedRepo ? { block: true, reason } : null
}

function callEnforcer(payload: JsonRecord, managedRepo: boolean): Promise<EnforcerResult | null> {
  return new Promise((resolve) => {
    const cwd = typeof payload.cwd === "string" ? payload.cwd : process.cwd()
    const child = spawn(SLOPGATE_ARGV[0], [...SLOPGATE_ARGV.slice(1), "handle", "--platform", "omp"], {
      cwd,
      env: process.env,
      stdio: ["pipe", "pipe", "pipe"],
    })
    let stdout = ""
    child.stdout.on("data", (chunk) => {
      stdout += chunk.toString()
    })
    child.stderr.resume()
    child.on("error", () => {
      resolve(failedEnforcerResult(managedRepo, "slopgate degraded mode: enforcer subprocess failed."))
    })
    child.on("close", (code) => {
      if (code !== 0) {
        resolve(failedEnforcerResult(managedRepo, "slopgate degraded mode: enforcer subprocess failed."))
        return
      }
      const output = stdout.trim()
      if (!output) {
        resolve(null)
        return
      }
      try {
        const parsed: unknown = JSON.parse(output)
        resolve(parseEnforcerResult(parsed))
      } catch (error) {
        if (!(error instanceof SyntaxError)) throw error
        resolve(failedEnforcerResult(managedRepo, "slopgate degraded mode: enforcer returned invalid JSON."))
      }
    })
    child.stdin.end(JSON.stringify(payload))
  })
}

function enforce(
  eventName: string,
  event: unknown,
  ctx: ExtensionContext,
  extra: JsonRecord = {},
): Promise<EnforcerResult | null> {
  return callEnforcer(enforcerPayload(eventName, event, ctx, extra), findManagedRepoRoot(ctx.cwd) !== null)
}

function resultGuidance(result: EnforcerResult | null): string {
  return result?.additionalContext || result?.context || result?.reason || ""
}

function sendSlopgateMessage(pi: ExtensionAPI, text: string, state: string): void {
  if (!text) return
  pi.sendMessage(
    { customType: MESSAGE_TYPE, content: text, display: true, details: { state, summary: text } },
    { triggerTurn: false },
  )
}

function advisory(pi: ExtensionAPI, ctx: ExtensionContext, result: EnforcerResult | null): void {
  const guidance = resultGuidance(result)
  if (!guidance) return
  sendSlopgateMessage(pi, guidance, "warning")
  if (ctx.hasUI) ctx.ui.notify(guidance, "warning")
}

function promptBlock(context: string): string {
  return `${PROMPT_HEADER}\n${context}\n\n${GUARD_MESSAGE}`
}

function isProtectedPath(value: string): boolean {
  const normalized = value.replace(/\\/g, "/")
  const fileName = normalized.split("/").pop() || ""
  return PROTECTED_NAMES.has(fileName)
    || PROTECTED_NAMES.has(normalized)
    || PROTECTED_SEGMENTS.some((segment) => normalized.includes(segment))
}

function toolPath(input: unknown): string | undefined {
  if (!isRecord(input)) return undefined
  for (const key of ["path", "file", "filePath", "file_path"]) {
    const value = input[key]
    if (typeof value === "string") return value
  }
  return undefined
}

function isBashField(key: string, value: unknown): boolean {
  switch (key) {
    case "command":
    case "cwd":
      return typeof value === "string"
    case "async":
    case "pty":
      return typeof value === "boolean"
    case "timeout":
      return typeof value === "number"
    case "env":
      return isRecord(value)
    default:
      return false
  }
}

function isProvenBashInput(value: unknown): value is JsonRecord {
  if (!isRecord(value) || typeof value.command !== "string") return false
  return Object.entries(value).every(([key, fieldValue]) => isBashField(key, fieldValue))
}

export default function slopgateOmpExtension(pi: ExtensionAPI): void {
  pi.registerMessageRenderer("slopgate-event", (message, options, theme) => {
    const details = isRecord(message.details) ? message.details : {}
    const summary = stringValue(details, "summary") || "Slopgate context captured."
    const state = stringValue(details, "state") || "context"
    const title = theme.bold(theme.fg(state === "blocked" ? "error" : "warning", `Slopgate · ${state}`))
    const box = new Box(1, 0, (text) => theme.bg("customMessageBg", text))
    box.addChild(new Text(options.expanded ? `${title}\n${summary}` : `${title} ${summary}`, 0, 0))
    return box
  })

  pi.registerCommand("slopgate-context", {
    description: "Show the latest Slopgate context injected into this session.",
    async handler(_args, ctx): Promise<void> {
      if (!lastSlopgateContext) {
        ctx.ui.notify("No Slopgate context has been captured yet.", "info")
        return
      }
      await ctx.ui.editor("Slopgate context", lastSlopgateContext)
    },
  })

  pi.on("session_start", async (event, ctx) => {
    lastSlopgateContext = ""
    lastStopGuidance = ""
    stopContinuationCounts.clear()
    const result = await enforce("session_start", event, ctx)
    lastSlopgateContext = result?.context || ""
  })

  pi.on("before_agent_start", (event) => {
    const context = [lastSlopgateContext, lastStopGuidance].filter(Boolean).join("\n\n")
    if (!context) return
    lastStopGuidance = ""
    return { systemPrompt: [...event.systemPrompt, promptBlock(context)] }
  })

  pi.on("input", async (event, ctx) => {
    const sessionId = currentSessionId(ctx)
    resetStopContinuationCount(sessionId)
    const result = await enforce("input", event, ctx)
    if (result?.block || result?.handled) {
      const reason = result.reason || "Blocked by slopgate"
      sendSlopgateMessage(pi, reason, "blocked")
      if (ctx.hasUI) ctx.ui.notify(reason, "warning")
      return { handled: true }
    }
    const replacement = result?.text
      || (result?.updatedInput ? stringValue(result.updatedInput, "text") : undefined)
      || (result?.updatedInput ? stringValue(result.updatedInput, "prompt") : undefined)
    if (replacement) return { text: replacement }
    advisory(pi, ctx, result)
  })

  pi.on("tool_call", async (event, ctx) => {
    const path = toolPath(event.input)
    if (path && isProtectedPath(path) && findManagedRepoRoot(ctx.cwd)) {
      return { block: true, reason: `Cannot modify Slopgate infrastructure: ${path}` }
    }
    const result = await enforce("tool_call", event, ctx)
    if (result?.block) return { block: true, reason: result.reason || "Blocked by slopgate" }
    const rewriteEnabled = process.env.SLOPGATE_OMP_INPUT_REWRITE === "1"
    if (rewriteEnabled && event.toolName === "bash" && isProvenBashInput(event.input)
      && isProvenBashInput(result?.updatedInput)) {
      return { input: result.updatedInput }
    }
    advisory(pi, ctx, result)
  })

  pi.on("tool_result", async (event, ctx) => {
    const result = await enforce("tool_result", event, ctx)
    const patch = result?.toolResultPatch
    if (patch?.details) {
      const details = isRecord(event.details) ? event.details : {}
      return { details: { ...details, ...patch.details } }
    }
    advisory(pi, ctx, result)
  })

  pi.on("session_stop", async (event, ctx) => {
    const sessionId = currentSessionId(ctx)
    const stopResponse = extractSessionStopResponse(event.last_assistant_message)
    const result = await enforce("session_stop", event, ctx, { stop_response: stopResponse })
    if (event.stop_hook_active) {
      resetStopContinuationCount(sessionId)
      advisory(pi, ctx, result)
      return
    }
    if (result?.continue || result?.block) {
      const count = stopContinuationCounts.get(sessionId) || 0
      if (count >= MAX_STOP_CONTINUATIONS) {
        resetStopContinuationCount(sessionId)
        sendSlopgateMessage(pi, CAP_NOTICE, "warning")
        if (ctx.hasUI) ctx.ui.notify(CAP_NOTICE, "warning")
        return
      }
      stopContinuationCounts.set(sessionId, count + 1)
      return { continue: true, additionalContext: resultGuidance(result) || "Continue after fixing Slopgate findings." }
    }
    if (resultGuidance(result)) {
      resetStopContinuationCount(sessionId)
      advisory(pi, ctx, result)
      return
    }
    resetStopContinuationCount(sessionId)
  })

  pi.on("turn_end", async (event, ctx) => {
    const result = await enforce("turn_end", event, ctx)
    lastStopGuidance = resultGuidance(result)
  })

  pi.on("agent_end", async (event, ctx) => {
    await enforce("agent_end", event, ctx)
  })

  pi.on("user_bash", async (event, ctx) => {
    const result = await enforce("user_bash", event, ctx)
    if (!result?.block) {
      advisory(pi, ctx, result)
      return
    }
    const output = result.reason || "Blocked by slopgate"
    sendSlopgateMessage(pi, output, "blocked")
    return {
      result: {
        output,
        exitCode: 1,
        cancelled: false,
        truncated: false,
        totalLines: 1,
        totalBytes: output.length,
        outputLines: 1,
        outputBytes: output.length,
      },
    }
  })

  pi.on("user_python", async (event, ctx) => {
    const result = await enforce("user_python", event, ctx)
    if (!result?.block) {
      advisory(pi, ctx, result)
      return
    }
    const output = result.reason || "Blocked by slopgate"
    sendSlopgateMessage(pi, output, "blocked")
    return {
      result: {
        output,
        exitCode: 1,
        cancelled: false,
        truncated: false,
        totalLines: 1,
        totalBytes: output.length,
        outputLines: 1,
        outputBytes: output.length,
        displayOutputs: [],
        stdinRequested: false,
      },
    }
  })
}
