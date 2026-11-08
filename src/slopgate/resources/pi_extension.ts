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
  platform: string
  kill(pid: number, signal: "SIGKILL"): void
}

import { spawn, type ChildProcess } from "node:child_process"
import { existsSync, realpathSync } from "node:fs"
import { homedir } from "node:os"
import { dirname, isAbsolute, join, relative, resolve as resolvePath } from "node:path"
import runtimeProcessValue from "node:process"
import { fileURLToPath } from "node:url"
import { Box, Text } from "@earendil-works/pi-tui"
import type { Component } from "@earendil-works/pi-tui"
import type { ExtensionAPI, ExtensionCommandContext, ToolResultEvent } from "@earendil-works/pi-coding-agent"

const runtimeProcess = runtimeProcessValue as NodeProcessLike

const SLOPGATE_ARGV = runtimeProcess.env.SLOPGATE_BIN ? [runtimeProcess.env.SLOPGATE_BIN] : ["__SLOPGATE_BIN__"]
const SLOPGATE_EVENT_MESSAGE_TYPE = "slopgate-event"
const DEFAULT_ENFORCER_TIMEOUT_MS = 10_000
const ENFORCER_CANCELLED = Symbol("slopgate-enforcer-cancelled")
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
const NATIVE_PI_UNICODE_SPACES = /[\u00A0\u2000-\u200A\u202F\u205F\u3000]/g
const NATIVE_PI_SHELL_DRIVE_PATH = /^\/(?:mnt\/|cygdrive\/)?([a-z])(?:\/(.*))?$/i

function normalizeNativePiShellPath(target: string): string {
  if (runtimeProcess.platform !== "win32") return target
  if (!target.startsWith("/") || target.startsWith("//") || target.includes("\\")) return target
  const match = NATIVE_PI_SHELL_DRIVE_PATH.exec(target)
  if (match === null) return target
  const suffix = (match[2] ?? "").replaceAll("/", "\\")
  return `${(match[1] ?? "").toUpperCase()}:\\${suffix}`
}

function normalizeNativePiPath(target: string, toolInput: boolean): string {
  let normalized = toolInput ? target.replace(NATIVE_PI_UNICODE_SPACES, " ") : target
  if (toolInput && normalized.startsWith("@")) normalized = normalized.slice(1)
  const shellPath = normalizeNativePiShellPath(normalized)
  if (shellPath === "~") return homedir()
  if (shellPath.startsWith("~/") || (runtimeProcess.platform === "win32" && shellPath.startsWith("~\\"))) {
    return join(homedir(), shellPath.slice(2))
  }
  if (/^file:\/\//.test(shellPath)) return fileURLToPath(shellPath)
  return shellPath
}

function resolveNativePiMutationPath(target: string, cwd: string): string {
  const normalizedTarget = normalizeNativePiPath(target, true)
  const normalizedCwd = normalizeNativePiPath(cwd, false)
  return isAbsolute(normalizedTarget)
    ? resolvePath(normalizedTarget)
    : resolvePath(normalizedCwd, normalizedTarget)
}


function isErrnoCode(error: unknown, codes: readonly string[]): boolean {
  if (typeof error !== "object" || error === null || !("code" in error)) return false
  const code = error.code
  return typeof code === "string" && codes.includes(code)
}

// Resolves symlinks on the longest existing prefix, so a not-yet-created target still maps to its real directory.
function realPathOrSelf(target: string): string {
  let existing = target
  const missing: string[] = []
  while (!existsSync(existing)) {
    const parent = dirname(existing)
    if (parent === existing) return target
    missing.unshift(existing.slice(parent.length + 1))
    existing = parent
  }
  try {
    return join(realpathSync(existing), ...missing)
  } catch (error) {
    if (isErrnoCode(error, ["ENOENT", "EACCES"])) return target
    throw error
  }
}

// The directory holding this module is the active, host-loaded package; legacy path markers no longer cover it.
const LOADED_PACKAGE_DIRS: readonly string[] = (() => {
  const loadedDir = resolvePath(dirname(fileURLToPath(import.meta.url)))
  return [...new Set([loadedDir, realPathOrSelf(loadedDir)])]
})()

function isInsideDir(target: string, dir: string): boolean {
  const rel = relative(dir, target)
  return rel === "" || (!rel.startsWith("..") && !isAbsolute(rel))
}

function isInsideLoadedPackage(target: string, cwd: string): boolean {
  let resolved: string
  try {
    resolved = resolveNativePiMutationPath(target, cwd)
  } catch {
    return false
  }
  return [resolved, realPathOrSelf(resolved)]
    .some((candidate) => LOADED_PACKAGE_DIRS.some((dir) => isInsideDir(candidate, dir)))
}

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
interface SessionContextState {
  readonly cwd: string
  context: string
  pendingPromptContext: string
  pendingGuidance: string
  lastContext: string
  promptRevision: number
  guidanceRevision: number
  prepared: { promptRevision: number; guidanceRevision: number } | undefined
  preToolContext: Map<string, string>
  initialization: Promise<void> | undefined
}

type EnforcerOutcome = PiEnforcerResult | null | typeof ENFORCER_CANCELLED

function createSessionContextState(cwd: string): SessionContextState {
  return {
    cwd,
    context: "",
    pendingPromptContext: "",
    pendingGuidance: "",
    lastContext: "",
    promptRevision: 0,
    guidanceRevision: 0,
    prepared: undefined,
    preToolContext: new Map(),
    initialization: undefined,
  }
}

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
  content?: ToolResultEvent["content"] | string
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
  signal?: AbortSignal
  ui?: PiUiLike
  sessionManager: {
    getSessionId(): string
  }
}

interface PiToolResultPatch {
  content?: ToolResultEvent["content"]
  details?: Record<string, unknown>
  isError?: boolean
}

interface PiInputTransformResult {
  action: "transform"
  text: string
}

interface PiBeforeAgentStartResult {
  systemPrompt?: string
}


type PiMessageRenderer = Parameters<ExtensionAPI["registerMessageRenderer"]>[1]

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
  if (event.details != null || event.isError != null) {
    const details = isRecord(event.details) ? event.details : undefined
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

function uniqueNonEmptyFragments(fragments: string[]): string[] {
  const seen = new Set<string>()
  const unique: string[] = []
  for (const fragment of fragments) {
    const normalized = fragment.trim()
    if (normalized && !seen.has(normalized)) {
      seen.add(normalized)
      unique.push(normalized)
    }
  }
  return unique
}

function combinedContext(state: SessionContextState): string {
  return uniqueNonEmptyFragments([
    state.context,
    state.pendingPromptContext,
    state.pendingGuidance,
  ]).join("\n\n")
}
function stringDetail(details: Record<string, unknown> | undefined, key: string): string {
  const value = details?.[key]
  return typeof value === "string" ? value : ""
}

function renderSlopgateMessage(
  message: Parameters<PiMessageRenderer>[0],
  options: Parameters<PiMessageRenderer>[1],
  theme: Parameters<PiMessageRenderer>[2],
): Component {
  const details = message.details && typeof message.details === "object" && !Array.isArray(message.details)
    ? (message.details as Record<string, unknown>)
    : undefined
  const state: string = stringDetail(details, "state")
  const eventName: string = stringDetail(details, "event")
  const reason: string = stringDetail(details, "reason")
  const summary: string = stringDetail(details, "summary") || "Slopgate context captured."

  const label: string = state === "blocked" ? "blocked" : state === "warning" ? "warning" : "context"
  const color = state === "blocked" ? "error" : state === "warning" ? "warning" : "accent"

  // Title: Slopgate · event_name  label
  const eventPart: string = eventName ? ` ${theme.fg("dim", `· ${eventName}`)}` : ""
  const title: string = `${theme.bold(theme.fg(color, "Slopgate"))}${eventPart} ${theme.fg("muted", label)}`

  const lines: string[] = [title]

  // Expanded: show full reason and metadata
  if (options.expanded && reason) {
    lines.push("", theme.fg("dim", reason))
  } else {
    lines.push(summary)
  }

  const box = new Box(1, 1, (text: string) => theme.bg("customMessageBg", text))
  box.addChild(new Text(lines.join("\n"), 0, 0))
  return box
}

function registerSlopgateMessageRenderer(pi: ExtensionAPI): void {
  pi.registerMessageRenderer(SLOPGATE_EVENT_MESSAGE_TYPE, renderSlopgateMessage)
}

function registerSlopgateContextCommand(
  pi: ExtensionAPI,
  contextFor: (ctx: ExtensionCommandContext) => string,
): void {
  pi.registerCommand("slopgate-context", {
    description: "Show the latest prepared Slopgate context for the current session.",
    async handler(_args: string, ctx: ExtensionCommandContext): Promise<void> {
      if (!ctx.hasUI) {
        return
      }
      const latestContext = contextFor(ctx)
      if (!latestContext) {
        ctx.ui.notify("No Slopgate context has been captured yet.", "info")
        return
      }
      await ctx.ui.editor("Slopgate context", latestContext)
    },
  })
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function mergeToolResultPatch(
  state: SessionContextState,
  event: PiEventLike,
  result: PiEnforcerResult | null,
): PiToolResultPatch | void {
  const toolCallId = event.toolCallId || ""
  const preToolContext = toolCallId ? state.preToolContext.get(toolCallId) || "" : ""
  if (toolCallId) {
    state.preToolContext.delete(toolCallId)
  }

  const findings = uniqueNonEmptyFragments([
    preToolContext,
    result?.context || "",
    result?.reason || "",
  ])
  const enforcerPatch = result?.tool_result_patch
  const merged: PiToolResultPatch = {}

  if (enforcerPatch?.isError !== undefined) {
    merged.isError = enforcerPatch.isError
  }
  const nativeDetails = isRecord(event.details) ? event.details : undefined
  const patchDetails = isRecord(enforcerPatch?.details) ? enforcerPatch.details : undefined
  if (nativeDetails || patchDetails) {
    merged.details = {
      ...(nativeDetails || {}),
      ...(patchDetails || {}),
    }
  }
  if (findings.length > 0) {
    const originalContent: ToolResultEvent["content"] = Array.isArray(event.content) ? event.content : []
    merged.content = [
      ...originalContent,
      { type: "text", text: `Slopgate findings:\n${findings.join("\n\n")}` },
    ]
  }
  return Object.keys(merged).length > 0 ? merged : undefined
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
  nativeSessionId: string,
): Record<string, unknown> {
  const cwd = cwdFromContext(ctx)
  const details = isRecord(event.details) ? event.details : undefined
  const stopResponse = eventName === "agent_end" || eventName === "turn_end"
    ? stopResponseFromEvent(event)
    : ""
  const toolResult = toolResultFromEvent(event)

  return {
    hook_event_name: eventName,
    tool_name: event.toolName || (typeof event.command === "string" ? "bash" : ""),
    tool_call_id: event.toolCallId || "",
    tool_input: toolInputFromEvent(event),
    cwd,
    session_id: runtimeProcess.env.SLOPGATE_SESSION_ID || nativeSessionId,
    transcript_path: null,
    prompt: promptFromEvent(event),
    tool_result: toolResult,
    isError: event.isError === true,
    details: event.details,
    stop_response: stopResponse || undefined,
    is_interrupt: details?.cancelled === true || details?.interrupted === true || undefined,
  }
}

function enforcerTimeoutMs(): number {
  const rawTimeout = runtimeProcess.env.SLOPGATE_ENFORCER_TIMEOUT_MS
  const parsedTimeout = rawTimeout === undefined ? DEFAULT_ENFORCER_TIMEOUT_MS : Number(rawTimeout)
  return Number.isFinite(parsedTimeout) && parsedTimeout > 0
    ? parsedTimeout
    : DEFAULT_ENFORCER_TIMEOUT_MS
}

function reportEnforcerFailure(
  eventName: string,
  sessionId: string,
  category: string,
  exitCode: number | null,
): void {
  const diagnostic = {
    service: "slopgate",
    event: eventName.slice(0, 64),
    session_id: sessionId.slice(0, 128),
    category,
    exit_code: exitCode,
  }
  console.error(`[slopgate] ${JSON.stringify(diagnostic)}`)
}

function killProcessTree(child: ChildProcess): void {
  const pid = child.pid
  if (pid == null) {
    child.kill("SIGKILL")
    return
  }
  if (runtimeProcess.platform === "win32") {
    spawn("taskkill", ["/PID", String(pid), "/T", "/F"], { stdio: "ignore" })
    child.kill("SIGKILL")
    return
  }
  try {
    runtimeProcess.kill(-pid, "SIGKILL")
  } catch {
    child.kill("SIGKILL")
  }
}

function callEnforcer(
  payload: Record<string, unknown>,
  managedRepo: boolean,
  eventName: string,
  sessionId: string,
  signals: (AbortSignal | undefined)[],
  activeChildren: Set<ChildProcess>,
): Promise<EnforcerOutcome> {
  return new Promise((resolve) => {
    const timeoutMs = enforcerTimeoutMs()
    const cwd = typeof payload.cwd === "string" ? payload.cwd : runtimeProcess.cwd()
    let child: ChildProcess | undefined
    let stdout = ""
    let inputLost = false
    let settled = false
    let termination: "cancelled" | "timeout" | undefined
    let timer: ReturnType<typeof setTimeout> | undefined
    const registeredSignals: AbortSignal[] = []

    const cleanup = (): void => {
      if (timer !== undefined) clearTimeout(timer)
      for (const signal of registeredSignals) {
        signal.removeEventListener("abort", onAbort)
      }
    }
    const finish = (result: EnforcerOutcome): void => {
      if (settled) return
      settled = true
      cleanup()
      resolve(result)
    }
    const degraded = (reason: string): EnforcerOutcome => managedRepo
      ? { block: true, reason }
      : null
    const terminate = (reason: "cancelled" | "timeout"): void => {
      if (settled || termination !== undefined) return
      termination = reason
      if (timer !== undefined) {
        clearTimeout(timer)
        timer = undefined
      }
      if (!child) {
        finish(reason === "cancelled"
          ? ENFORCER_CANCELLED
          : degraded("slopgate degraded mode: enforcer subprocess timed out in managed repo."))
        return
      }
      child.stdin?.destroy()
      child.stdout?.destroy()
      killProcessTree(child)
    }
    const onAbort = (): void => terminate("cancelled")

    if (signals.some((signal) => signal?.aborted)) {
      finish(ENFORCER_CANCELLED)
      return
    }
    for (const signal of new Set(signals.filter((value): value is AbortSignal => value !== undefined))) {
      signal.addEventListener("abort", onAbort, { once: true })
      registeredSignals.push(signal)
    }

    timer = setTimeout(() => {
      if (settled) return
      reportEnforcerFailure(eventName, sessionId, "timeout", null)
      terminate("timeout")
    }, timeoutMs)
    timer.unref?.()

    try {
      child = spawn(
        SLOPGATE_ARGV[0],
        [...SLOPGATE_ARGV.slice(1), "handle", "--platform", "pi"],
        {
          cwd,
          env: runtimeProcess.env,
          detached: runtimeProcess.platform !== "win32",
          stdio: ["pipe", "pipe", "ignore"],
        },
      )
      activeChildren.add(child)
      child.stdout?.on("data", (chunk: string | Uint8Array) => {
        stdout += chunkToUtf8(chunk)
      })
      if (child.stdin) {
        child.stdin.on("error", () => {
          inputLost = true
        })
      } else {
        inputLost = true
      }
      child.once("error", () => {
        if (child) activeChildren.delete(child)
        if (termination === "cancelled") {
          finish(ENFORCER_CANCELLED)
          return
        }
        if (termination === "timeout") {
          finish(degraded("slopgate degraded mode: enforcer subprocess timed out in managed repo."))
          return
        }
        reportEnforcerFailure(eventName, sessionId, "spawn_failed", null)
        finish(degraded("slopgate degraded mode: enforcer subprocess failed in managed repo."))
      })
      child.once("close", (exitCode: number | null) => {
        if (child) activeChildren.delete(child)
        if (termination === "cancelled") {
          finish(ENFORCER_CANCELLED)
          return
        }
        if (termination === "timeout") {
          finish(degraded("slopgate degraded mode: enforcer subprocess timed out in managed repo."))
          return
        }
        if (exitCode !== 0) {
          reportEnforcerFailure(eventName, sessionId, "nonzero_exit", exitCode)
          finish(degraded("slopgate degraded mode: enforcer subprocess failed in managed repo."))
          return
        }
        if (inputLost) {
          reportEnforcerFailure(eventName, sessionId, "stdin_lost", exitCode)
          finish(degraded("slopgate degraded mode: enforcer did not read its input in managed repo."))
          return
        }
        const trimmed = stdout.trim()
        if (!trimmed) {
          finish(null)
          return
        }
        try {
          finish(JSON.parse(trimmed) as PiEnforcerResult)
        } catch {
          reportEnforcerFailure(eventName, sessionId, "invalid_json", exitCode)
          finish(degraded("slopgate degraded mode: enforcer returned invalid JSON in managed repo."))
        }
      })
      if (child.stdin) {
        try {
          child.stdin.end(JSON.stringify(payload))
        } catch {
          inputLost = true
        }
      }
    } catch {
      if (child) activeChildren.delete(child)
      reportEnforcerFailure(eventName, sessionId, "spawn_failed", null)
      finish(degraded("slopgate degraded mode: enforcer subprocess failed in managed repo."))
    }
  })
}

async function enforce(
  eventName: string,
  event: PiEventLike,
  ctx: PiContextLike,
  shutdownSignal: AbortSignal,
  activeChildren: Set<ChildProcess>,
): Promise<EnforcerOutcome> {
  const cwd = cwdFromContext(ctx)
  const nativeSessionId = ctx.sessionManager.getSessionId()
  const managedRepo = findManagedRepoRoot(cwd) !== null
  try {
    const payload = enforcerPayload(eventName, event, ctx, nativeSessionId)
    return await callEnforcer(
      payload,
      managedRepo,
      eventName,
      nativeSessionId,
      [ctx.signal, shutdownSignal],
      activeChildren,
    )
  } catch {
    reportEnforcerFailure(eventName, nativeSessionId, "payload_failed", null)
    return managedRepo
      ? { block: true, reason: "slopgate degraded mode: enforcer subprocess failed in managed repo." }
      : null
  }
}

export default function slopgatePiExtension(pi: ExtensionAPI) {
  const sessionStates = new Map<string, SessionContextState>()
  let shutdownController = new AbortController()
  const activeChildren = new Set<ChildProcess>()

  const stateFor = (ctx: PiContextLike): SessionContextState => {
    const sessionId = ctx.sessionManager.getSessionId()
    const cwd = cwdFromContext(ctx)
    const existing = sessionStates.get(sessionId)
    if (existing && existing.cwd === cwd) {
      return existing
    }
    const state = createSessionContextState(cwd)
    sessionStates.set(sessionId, state)
    return state
  }

  const replacePendingGuidance = (state: SessionContextState, value: string): void => {
    const guidance = value.trim()
    if (!guidance) return
    state.pendingGuidance = guidance
    state.guidanceRevision += 1
  }

  const clearPendingState = (state: SessionContextState): void => {
    state.pendingPromptContext = ""
    state.pendingGuidance = ""
    state.promptRevision += 1
    state.guidanceRevision += 1
    state.prepared = undefined
    state.preToolContext.clear()
  }

  const clearPreparedState = (state: SessionContextState): void => {
    const prepared = state.prepared
    if (!prepared) return
    if (state.promptRevision === prepared.promptRevision) {
      state.pendingPromptContext = ""
    }
    if (state.guidanceRevision === prepared.guidanceRevision) {
      state.pendingGuidance = ""
    }
    state.prepared = undefined
  }

  const initializeSession = (
    state: SessionContextState,
    event: PiEventLike,
    ctx: PiContextLike,
  ): Promise<void> => {
    if (state.initialization) return state.initialization
    const initialization = Promise.resolve().then(async () => {
      const result = await enforce("session_start", event, ctx, shutdownController.signal, activeChildren)
      if (result === ENFORCER_CANCELLED) return
      if (result?.context) {
        state.context = result.context
      }
      if (result?.block) {
        const reason = result.reason || "Blocked by Slopgate during session initialization."
        replacePendingGuidance(state, reason)
        if (ctx.hasUI && ctx.ui?.notify) {
          ctx.ui.notify(reason, "warning")
        } else {
          console.error(`[slopgate] ${reason}`)
        }
      }
    })
    state.initialization = initialization
    return initialization
  }

  registerSlopgateMessageRenderer(pi)
  registerSlopgateContextCommand(pi, (ctx) => stateFor(ctx).lastContext)

  pi.on("session_start", async (event, ctx) => {
    const state = stateFor(ctx)
    await initializeSession(state, event, ctx)
  })

  pi.on("tool_call", async (event, ctx) => {
    const state = stateFor(ctx)
    const toolName = event.toolName || ""
    if (toolName === "write" || toolName === "edit" || toolName === "replace" || toolName === "bash") {
      const toolPath = toolPathFromEvent(event)
      const cwd = cwdFromContext(ctx)
      if (toolPath && (isInsideLoadedPackage(toolPath, cwd)
        || (isSlopgatePath(toolPath) && findManagedRepoRoot(cwd)))) {
        return {
          block: true,
          reason: `Cannot modify slopgate infrastructure: ${toolPath}. Fix the flagged issue instead.`,
        }
      }
    }

    const result = await enforce("tool_call", event, ctx, shutdownController.signal, activeChildren)
    if (result === ENFORCER_CANCELLED) return
    applyUpdatedInput(event, result?.updated_input)
    if (result?.block) {
      return { block: true, reason: result.reason || "Blocked by slopgate" }
    }
    const toolCallId = event.toolCallId
    if (toolCallId && result?.context?.trim()) {
      state.preToolContext.set(toolCallId, result.context)
    }
  })

  pi.on("tool_result", async (event, ctx) => {
    const state = stateFor(ctx)
    const result = await enforce("tool_result", event, ctx, shutdownController.signal, activeChildren)
    if (result === ENFORCER_CANCELLED) {
      if (event.toolCallId) state.preToolContext.delete(event.toolCallId)
      return
    }
    return mergeToolResultPatch(state, event, result)
  })

  pi.on("input", async (event, ctx) => {
    const state = stateFor(ctx)
    const result = await enforce("input", event, ctx, shutdownController.signal, activeChildren)
    if (result === ENFORCER_CANCELLED) return

    state.pendingPromptContext = result?.block ? "" : result?.context || ""
    state.promptRevision += 1
    if (result?.block) {
      const reason = result.reason || "Blocked by slopgate"
      if (ctx.hasUI && ctx.ui?.notify) {
        ctx.ui.notify(reason, "warning")
      } else {
        console.error(`[slopgate] input blocked: ${reason}`)
      }
      return { action: "handled" }
    }
    return inputTransformFromUpdatedInput(result?.updated_input) || undefined
  })

  pi.on("before_agent_start", (event, ctx) => {
    const state = stateFor(ctx)
    const promptContext = combinedContext(state)
    state.prepared = {
      promptRevision: state.promptRevision,
      guidanceRevision: state.guidanceRevision,
    }
    if (!promptContext) return
    state.lastContext = promptContext
    const result: PiBeforeAgentStartResult = {
      systemPrompt: appendSlopgateSystemPrompt(event.systemPrompt, promptContext),
    }
    return result
  })

  pi.on("turn_end", async (event, ctx) => {
    const state = stateFor(ctx)
    clearPreparedState(state)
    const result = await enforce("turn_end", event, ctx, shutdownController.signal, activeChildren)
    if (result === ENFORCER_CANCELLED) return
    replacePendingGuidance(state, result?.context || result?.reason || "")
  })

  pi.on("agent_end", async (event, ctx) => {
    const state = stateFor(ctx)
    const result = await enforce("agent_end", event, ctx, shutdownController.signal, activeChildren)
    state.preToolContext.clear()
    if (result === ENFORCER_CANCELLED) return
    replacePendingGuidance(state, result?.context || result?.reason || "")
  })

  pi.on("agent_settled", (_event, ctx) => {
    stateFor(ctx).preToolContext.clear()
  })

  pi.on("session_tree", (_event, ctx) => {
    clearPendingState(stateFor(ctx))
  })

  pi.on("session_shutdown", () => {
    sessionStates.clear()
    // Swap before aborting: later sessions in this process must not inherit a dead signal.
    const controller = shutdownController
    shutdownController = new AbortController()
    controller.abort()
  })

  pi.on("user_bash", async (event, ctx) => {
    const state = stateFor(ctx)
    const result = await enforce("user_bash", event, ctx, shutdownController.signal, activeChildren)
    if (result === ENFORCER_CANCELLED) return
    if (result?.block) {
      return {
        result: {
          output: result.reason || "Blocked by slopgate",
          exitCode: 1,
          cancelled: false,
          truncated: false,
        },
      }
    }
    replacePendingGuidance(state, result?.context || "")
  })
}
