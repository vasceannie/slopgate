/**
 * OMP Slopgate Extension
 *
 * Bridges OMP extension events to `slopgate handle --platform omp`.
 *
 * Findings reach the model through per-request delivery: system-prompt
 * context at `before_agent_start`, and findings appended to the native tool
 * result at `tool_result`. The bridge never injects custom chat messages.
 */

import { spawn, type ChildProcess } from "node:child_process"
import { existsSync, realpathSync } from "node:fs"
import { dirname, isAbsolute, join, relative, resolve as resolvePath } from "node:path"
import process from "node:process"
import { fileURLToPath } from "node:url"

import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent"
import type { ExtensionContext } from "@oh-my-pi/pi-coding-agent"
import type { ToolResultEvent, ToolResultEventResult } from "@oh-my-pi/pi-coding-agent"
import { resolveToCwd } from "@oh-my-pi/pi-coding-agent/tools/path-utils"
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

type EnforcerOutcome = EnforcerResult | null | typeof ENFORCER_CANCELLED

type PreparedRevisions = {
  readonly promptRevision: number
  readonly guidanceRevision: number
}

interface SessionContextState {
  readonly cwd: string
  context: string
  pendingPromptContext: string
  pendingGuidance: string
  lastContext: string
  promptRevision: number
  guidanceRevision: number
  prepared: PreparedRevisions | undefined
  preToolContext: Map<string, string>
  initialization: Promise<void> | undefined
  stopContinuations: number
}

type StateContext = Pick<ExtensionContext, "cwd" | "sessionManager">
type TimerCanceller = () => void
type StartTimer = (delayMs: number, onExpire: () => void) => TimerCanceller
type ReportFailure = (category: string, exitCode: number | null) => void

type EnforcerCall = {
  readonly body: string
  readonly cwd: string
  readonly managedRepo: boolean
  readonly report: ReportFailure
  readonly signals: readonly AbortSignal[]
  readonly startTimer: StartTimer
}

const SLOPGATE_ARGV = process.env.SLOPGATE_BIN ? [process.env.SLOPGATE_BIN] : ["__SLOPGATE_BIN__"]
const DEFAULT_ENFORCER_TIMEOUT_MS = 10_000
const ENFORCER_CANCELLED = Symbol("slopgate-enforcer-cancelled")
const MAX_STOP_CONTINUATIONS = 8
const MAX_LOG_EVENT_LENGTH = 64
const MAX_LOG_SESSION_LENGTH = 128
const CAP_NOTICE = "slopgate: continuation cap reached (8); fix remaining findings manually."
const PROMPT_HEADER = "Slopgate hook context for this turn:"
const GUARD_MESSAGE = "Fix Slopgate findings directly; do not disable or bypass its rules."
const FINDINGS_HEADER = "Slopgate findings:"
const REASON_TIMED_OUT = "slopgate degraded mode: enforcer subprocess timed out in managed repo."
const REASON_FAILED = "slopgate degraded mode: enforcer subprocess failed in managed repo."
const REASON_INPUT_LOST = "slopgate degraded mode: enforcer did not read its input in managed repo."
const REASON_INVALID_JSON = "slopgate degraded mode: enforcer returned invalid JSON in managed repo."
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
  // Resolve the way the host write tool does (@, :, file://, ~, relative); a target the host rejects cannot reach the package.
  let resolved: string
  try {
    resolved = resolveToCwd(target, cwd)
  } catch {
    return false
  }
  return [resolved, realPathOrSelf(resolved)]
    .some((candidate) => LOADED_PACKAGE_DIRS.some((dir) => isInsideDir(candidate, dir)))
}

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

function currentSessionId(ctx: StateContext): string {
  return process.env.SLOPGATE_SESSION_ID || ctx.sessionManager.getSessionId()
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
    cwd: ctx.cwd,
    session_id: currentSessionId(ctx),
    transcript_path: null,
    prompt: stringValue(raw, "text") || "",
    ...extra,
  }
}

function resultGuidance(result: EnforcerResult | null): string {
  return result?.additionalContext || result?.context || result?.reason || ""
}

function promptBlock(context: string): string {
  return `${PROMPT_HEADER}\n${context}\n\n${GUARD_MESSAGE}`
}

function uniqueNonEmptyFragments(fragments: readonly string[]): string[] {
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

function isReviveStart(event: unknown): boolean {
  return isRecord(event) && stringValue(event, "reason") === "revive"
}

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
    stopContinuations: 0,
  }
}

function replacePendingGuidance(state: SessionContextState, value: string): void {
  const guidance = value.trim()
  if (!guidance) return
  state.pendingGuidance = guidance
  state.guidanceRevision += 1
}

function resetStopContinuationCount(state: SessionContextState): void {
  state.stopContinuations = 0
}

function clearPendingState(state: SessionContextState): void {
  state.pendingPromptContext = ""
  state.pendingGuidance = ""
  state.promptRevision += 1
  state.guidanceRevision += 1
  state.prepared = undefined
  state.preToolContext.clear()
  resetStopContinuationCount(state)
}

function clearPreparedState(state: SessionContextState): void {
  const prepared = state.prepared
  if (!prepared) return
  if (state.promptRevision === prepared.promptRevision) state.pendingPromptContext = ""
  if (state.guidanceRevision === prepared.guidanceRevision) state.pendingGuidance = ""
  state.prepared = undefined
}

function rememberPreToolContext(state: SessionContextState, toolCallId: string, context: string | undefined): void {
  if (toolCallId && context?.trim()) state.preToolContext.set(toolCallId, context)
}

function notifyUser(ctx: ExtensionContext, message: string): void {
  if (message && ctx.hasUI) ctx.ui.notify(message, "warning")
}

function notifyOrStderr(ctx: ExtensionContext, message: string, stderrLine: string): void {
  if (ctx.hasUI) ctx.ui.notify(message, "warning")
  else process.stderr.write(`${stderrLine}\n`)
}

function mergeToolResult(
  event: ToolResultEvent,
  preToolContext: string,
  result: EnforcerResult | null,
): ToolResultEventResult | undefined {
  const findings = uniqueNonEmptyFragments([preToolContext, result?.context ?? "", result?.reason ?? ""])
  const patch = result?.toolResultPatch
  const content = findings.length > 0
    ? [...event.content, { type: "text" as const, text: `${FINDINGS_HEADER}\n${findings.join("\n\n")}` }]
    : undefined
  const details = patch?.details
    ? { ...(isRecord(event.details) ? event.details : {}), ...patch.details }
    : undefined
  const isError = patch?.isError
  if (content === undefined && details === undefined && isError === undefined) return undefined
  return { content, details, isError }
}

function isProtectedPath(value: string): boolean {
  const normalized = value.replace(/\\/g, "/")
  const fileName = normalized.split("/").pop() || ""
  return PROTECTED_NAMES.has(fileName)
    || PROTECTED_NAMES.has(normalized)
    || PROTECTED_SEGMENTS.some((segment) => normalized.includes(segment))
}

function directMutationPaths(input: unknown): string[] {
  if (!isRecord(input)) return []
  const paths: string[] = []
  for (const key of ["path", "file", "filePath", "file_path"]) {
    const value = input[key]
    if (typeof value === "string") paths.push(value)
  }
  if (Array.isArray(input.paths)) {
    for (const value of input.paths) {
      if (typeof value === "string") paths.push(value)
    }
  }
  return paths
}

function applyPatchEnvelopePaths(envelope: string): string[] {
  return [...envelope.matchAll(/^\*\*\* (?:Add|Update|Delete) File:\s*(.+)$/gm)]
    .map((match) => match[1]?.trim())
    .filter((value): value is string => Boolean(value))
}

// Mirrors the native hashline header grammar (@oh-my-pi/pi-coding-agent edit/index.ts
// extractApprovalPaths): current-format headers start a line as `[path]` or `[path#tag]`.
function hashlineEnvelopePaths(envelope: string): string[] {
  return [...envelope.matchAll(/^\[([^#\r\n]+)(?:#[0-9a-fA-F]{4})?\]/gm)]
    .map((match) => match[1]?.trim())
    .filter((value): value is string => Boolean(value))
}

function mutationTargetPaths(toolName: string, input: unknown): string[] {
  const paths = directMutationPaths(input)
  if (toolName !== "edit" && toolName !== "apply_patch") return paths
  const envelope = isRecord(input) ? stringValue(input, "input") : undefined
  if (envelope === undefined) return paths
  return [...paths, ...applyPatchEnvelopePaths(envelope), ...hashlineEnvelopePaths(envelope)]
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
      return isRecord(value) && Object.values(value).every((entry) => typeof entry === "string")
    default:
      return false
  }
}

function isProvenBashInput(value: unknown): value is JsonRecord {
  if (!isRecord(value) || typeof value.command !== "string") return false
  return Object.entries(value).every(([key, fieldValue]) => isBashField(key, fieldValue))
}

function enforcerTimeoutMs(): number {
  const rawTimeout = process.env.SLOPGATE_ENFORCER_TIMEOUT_MS
  const parsedTimeout = rawTimeout === undefined ? DEFAULT_ENFORCER_TIMEOUT_MS : Number(rawTimeout)
  return Number.isFinite(parsedTimeout) && parsedTimeout > 0 ? parsedTimeout : DEFAULT_ENFORCER_TIMEOUT_MS
}

function ignoreError(): void {}

function killProcessTree(child: ChildProcess): void {
  const pid = child.pid
  if (pid === undefined) {
    child.kill("SIGKILL")
    return
  }
  if (process.platform === "win32") {
    spawn("taskkill", ["/PID", String(pid), "/T", "/F"], { stdio: "ignore", windowsHide: true }).on("error", ignoreError)
    child.kill("SIGKILL")
    return
  }
  try {
    process.kill(-pid, "SIGKILL")
  } catch {
    child.kill("SIGKILL")
  }
}

function startTimerFor(ctx: ExtensionContext): StartTimer {
  return (delayMs, onExpire) => {
    if (typeof ctx.setTimeout === "function" && typeof ctx.clearTimer === "function") {
      const handle = ctx.setTimeout(onExpire, delayMs)
      return () => ctx.clearTimer(handle)
    }
    const handle = setTimeout(onExpire, delayMs)
    handle.unref()
    return () => clearTimeout(handle)
  }
}

function callEnforcer(call: EnforcerCall): Promise<EnforcerOutcome> {
  return new Promise((resolve) => {
    let child: ChildProcess | undefined
    let stdout = ""
    let inputLost = false
    let settled = false
    let termination: "cancelled" | "timeout" | undefined
    let cancelTimer: TimerCanceller | undefined

    const degraded = (reason: string): EnforcerOutcome => (call.managedRepo ? { block: true, reason } : null)
    const terminationOutcome = (reason: "cancelled" | "timeout"): EnforcerOutcome =>
      reason === "cancelled" ? ENFORCER_CANCELLED : degraded(REASON_TIMED_OUT)
    const stopTimer = (): void => {
      cancelTimer?.()
      cancelTimer = undefined
    }
    const cleanup = (): void => {
      stopTimer()
      for (const signal of call.signals) signal.removeEventListener("abort", onAbort)
    }
    const finish = (outcome: EnforcerOutcome): void => {
      if (settled) return
      settled = true
      cleanup()
      resolve(outcome)
    }
    const terminate = (reason: "cancelled" | "timeout"): void => {
      if (settled || termination !== undefined) return
      termination = reason
      stopTimer()
      if (!child) {
        finish(terminationOutcome(reason))
        return
      }
      // Reap before settling: the close handler resolves once the tree is dead.
      child.stdin?.destroy()
      child.stdout?.destroy()
      killProcessTree(child)
    }
    const onAbort = (): void => terminate("cancelled")

    if (call.signals.some((signal) => signal.aborted)) {
      finish(ENFORCER_CANCELLED)
      return
    }
    for (const signal of call.signals) signal.addEventListener("abort", onAbort, { once: true })
    cancelTimer = call.startTimer(enforcerTimeoutMs(), () => {
      if (settled) return
      call.report("timeout", null)
      terminate("timeout")
    })

    try {
      const spawned = spawn(SLOPGATE_ARGV[0], [...SLOPGATE_ARGV.slice(1), "handle", "--platform", "omp"], {
        cwd: call.cwd,
        env: process.env,
        detached: process.platform !== "win32",
        stdio: ["pipe", "pipe", "ignore"],
      })
      child = spawned
      spawned.stdout?.setEncoding("utf8")
      spawned.stdout?.on("data", (chunk: string) => {
        stdout += chunk
      })
      // Attach before writing: an enforcer that exits early would otherwise crash the host.
      if (spawned.stdin) {
        spawned.stdin.on("error", () => {
          inputLost = true
        })
      } else {
        inputLost = true
      }
      spawned.once("error", () => {
        if (termination !== undefined) {
          finish(terminationOutcome(termination))
          return
        }
        call.report("spawn_failed", null)
        finish(degraded(REASON_FAILED))
      })
      spawned.once("close", (exitCode: number | null) => {
        if (termination !== undefined) {
          finish(terminationOutcome(termination))
          return
        }
        if (exitCode !== 0) {
          call.report("nonzero_exit", exitCode)
          finish(degraded(REASON_FAILED))
          return
        }
        if (inputLost) {
          // A clean exit is not a verdict when the enforcer never saw the whole payload.
          call.report("stdin_lost", exitCode)
          finish(degraded(REASON_INPUT_LOST))
          return
        }
        const output = stdout.trim()
        if (!output) {
          finish(null)
          return
        }
        try {
          finish(parseEnforcerResult(JSON.parse(output)))
        } catch {
          call.report("invalid_json", exitCode)
          finish(degraded(REASON_INVALID_JSON))
        }
      })
      if (spawned.stdin) {
        try {
          spawned.stdin.end(call.body)
        } catch {
          inputLost = true
        }
      }
    } catch {
      call.report("spawn_failed", null)
      finish(degraded(REASON_FAILED))
    }
  })
}

async function enforce(
  pi: ExtensionAPI,
  signals: readonly AbortSignal[],
  eventName: string,
  event: unknown,
  ctx: ExtensionContext,
  extra: JsonRecord = {},
): Promise<EnforcerOutcome> {
  const managedRepo = findManagedRepoRoot(ctx.cwd) !== null
  const sessionId = currentSessionId(ctx)
  const report: ReportFailure = (category, exitCode) => {
    // Bounded structured fields only: never prompts, payloads, or child stderr.
    pi.logger.warn("slopgate enforcer failure", {
      service: "slopgate",
      event: eventName.slice(0, MAX_LOG_EVENT_LENGTH),
      session_id: sessionId.slice(0, MAX_LOG_SESSION_LENGTH),
      category,
      exit_code: exitCode,
    })
  }
  try {
    return await callEnforcer({
      body: JSON.stringify(enforcerPayload(eventName, event, ctx, extra)),
      cwd: ctx.cwd,
      managedRepo,
      report,
      signals,
      startTimer: startTimerFor(ctx),
    })
  } catch {
    report("payload_failed", null)
    return managedRepo ? { block: true, reason: REASON_FAILED } : null
  }
}

function blockedBashResult(output: string) {
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
}

function blockedPythonResult(output: string) {
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
}

export default function slopgateOmpExtension(pi: ExtensionAPI): void {
  // State is owned by this factory instance; two factories in one process never share it.
  const sessionStates = new Map<string, SessionContextState>()
  let shutdownController = new AbortController()

  const stateFor = (ctx: StateContext): SessionContextState => {
    const sessionId = ctx.sessionManager.getSessionId()
    const existing = sessionStates.get(sessionId)
    if (existing && existing.cwd === ctx.cwd) return existing
    const state = createSessionContextState(ctx.cwd)
    sessionStates.set(sessionId, state)
    return state
  }

  const evaluate = (
    eventName: string,
    event: unknown,
    ctx: ExtensionContext,
    extra: JsonRecord = {},
    eventSignal?: AbortSignal,
  ): Promise<EnforcerOutcome> => {
    const signals = eventSignal ? [shutdownController.signal, eventSignal] : [shutdownController.signal]
    return enforce(pi, signals, eventName, event, ctx, extra)
  }

  const evaluateStartup = async (
    state: SessionContextState,
    event: unknown,
    ctx: ExtensionContext,
  ): Promise<void> => {
    const result = await evaluate("session_start", event, ctx)
    if (result === ENFORCER_CANCELLED) return
    if (result?.context) state.context = result.context
    if (result?.block) {
      // Keep the degraded reason for the next real request; startup is never retried.
      const reason = result.reason || "Blocked by Slopgate during session initialization."
      replacePendingGuidance(state, reason)
      notifyOrStderr(ctx, reason, `[slopgate] ${reason}`)
    }
  }

  const initializeSession = (
    state: SessionContextState,
    event: unknown,
    ctx: ExtensionContext,
  ): Promise<void> => {
    if (state.initialization) return state.initialization
    const initialization = evaluateStartup(state, event, ctx)
    state.initialization = initialization
    return initialization
  }

  const navigate = async (event: unknown, ctx: ExtensionContext): Promise<void> => {
    const state = stateFor(ctx)
    clearPendingState(state)
    if (!state.initialization) await initializeSession(state, event, ctx)
  }

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
    description: "Show the latest Slopgate context prepared for this session.",
    async handler(_args, ctx): Promise<void> {
      const latestContext = stateFor(ctx).lastContext
      if (!latestContext) {
        ctx.ui.notify("No Slopgate context has been captured yet.", "info")
        return
      }
      await ctx.ui.editor("Slopgate context", latestContext)
    },
  })

  pi.on("session_start", async (event, ctx) => {
    await initializeSession(stateFor(ctx), event, ctx)
  })

  pi.on("session_switch", async (event, ctx) => {
    await navigate(event, ctx)
  })

  pi.on("session_branch", async (event, ctx) => {
    await navigate(event, ctx)
  })

  pi.on("session_tree", async (event, ctx) => {
    await navigate(event, ctx)
  })

  pi.on("session_shutdown", () => {
    sessionStates.clear()
    const controller = shutdownController
    shutdownController = new AbortController()
    controller.abort()
  })

  pi.on("input", async (event, ctx) => {
    const state = stateFor(ctx)
    resetStopContinuationCount(state)
    const result = await evaluate("input", event, ctx)
    if (result === ENFORCER_CANCELLED) return
    const denied = Boolean(result?.block || result?.handled)
    // A later input supersedes context staged by an earlier UI-only slash command.
    state.pendingPromptContext = denied ? "" : result?.context || ""
    state.promptRevision += 1
    if (denied) {
      const reason = result?.reason || "Blocked by slopgate"
      notifyOrStderr(ctx, reason, `[slopgate] input blocked: ${reason}`)
      return { handled: true }
    }
    const replacement = result?.text
      || (result?.updatedInput ? stringValue(result.updatedInput, "text") : undefined)
      || (result?.updatedInput ? stringValue(result.updatedInput, "prompt") : undefined)
    if (replacement) return { text: replacement }
  })

  pi.on("before_agent_start", (event, ctx) => {
    if (isReviveStart(event)) return
    const state = stateFor(ctx)
    const context = combinedContext(state)
    // Preparation can be retried or discarded, so nothing is consumed until turn_end.
    state.prepared = { promptRevision: state.promptRevision, guidanceRevision: state.guidanceRevision }
    if (!context) return
    state.lastContext = context
    return { systemPrompt: [...event.systemPrompt, promptBlock(context)] }
  })

  pi.on("tool_call", async (event, ctx) => {
    const state = stateFor(ctx)
    const toolName = event.toolName
    const targetPaths = mutationTargetPaths(toolName, event.input)
    const isMutation = toolName === "write" || toolName === "edit" || toolName === "apply_patch"
    if (isMutation) {
      // The loaded package is shared across projects, so it is protected from any cwd; repo-local paths stay enrollment-gated.
      const packageTarget = targetPaths.find((targetPath) => isInsideLoadedPackage(targetPath, ctx.cwd))
      const repoTarget = packageTarget === undefined && findManagedRepoRoot(ctx.cwd) !== null
        ? targetPaths.find((targetPath) => isProtectedPath(targetPath))
        : undefined
      const protectedPath = packageTarget ?? repoTarget
      if (protectedPath !== undefined) {
        return { block: true, reason: `Cannot modify Slopgate infrastructure: ${protectedPath}` }
      }
    }
    const result = await evaluate("tool_call", event, ctx)
    if (result === ENFORCER_CANCELLED) return
    if (result?.block) return { block: true, reason: result.reason || "Blocked by slopgate" }
    rememberPreToolContext(state, event.toolCallId, result?.context)
    const rewriteEnabled = process.env.SLOPGATE_OMP_INPUT_REWRITE === "1"
    if (rewriteEnabled && event.toolName === "bash" && isProvenBashInput(event.input)
      && isProvenBashInput(result?.updatedInput)) {
      return { input: result.updatedInput }
    }
  })

  pi.on("tool_result", async (event, ctx) => {
    const state = stateFor(ctx)
    const result = await evaluate("tool_result", event, ctx)
    const preToolContext = state.preToolContext.get(event.toolCallId) ?? ""
    state.preToolContext.delete(event.toolCallId)
    if (result === ENFORCER_CANCELLED) return
    return mergeToolResult(event, preToolContext, result)
  })

  pi.on("session_stop", async (event, ctx) => {
    const state = stateFor(ctx)
    const stopResponse = extractSessionStopResponse(event.last_assistant_message)
    const result = await evaluate("session_stop", event, ctx, { stop_response: stopResponse }, event.signal)
    if (result === ENFORCER_CANCELLED) return
    if (event.stop_hook_active) {
      resetStopContinuationCount(state)
      replacePendingGuidance(state, resultGuidance(result))
      notifyUser(ctx, resultGuidance(result))
      return
    }
    if (result?.continue || result?.block) {
      if (state.stopContinuations >= MAX_STOP_CONTINUATIONS) {
        resetStopContinuationCount(state)
        notifyUser(ctx, CAP_NOTICE)
        return
      }
      state.stopContinuations += 1
      return { continue: true, additionalContext: resultGuidance(result) || "Continue after fixing Slopgate findings." }
    }
    resetStopContinuationCount(state)
    // Non-blocking stop advice reaches the model on the next real prompt, never as a history entry.
    replacePendingGuidance(state, resultGuidance(result))
    notifyUser(ctx, resultGuidance(result))
  })

  pi.on("turn_end", async (event, ctx) => {
    const state = stateFor(ctx)
    clearPreparedState(state)
    const result = await evaluate("turn_end", event, ctx)
    if (result === ENFORCER_CANCELLED) return
    replacePendingGuidance(state, result?.context || result?.reason || "")
  })

  pi.on("agent_end", async (event, ctx) => {
    const state = stateFor(ctx)
    const result = await evaluate("agent_end", event, ctx)
    state.preToolContext.clear()
    if (result === ENFORCER_CANCELLED) return
    replacePendingGuidance(state, result?.context || result?.reason || "")
  })

  pi.on("user_bash", async (event, ctx) => {
    const state = stateFor(ctx)
    const result = await evaluate("user_bash", event, ctx)
    if (result === ENFORCER_CANCELLED) return
    if (result?.block) return blockedBashResult(result.reason || "Blocked by slopgate")
    replacePendingGuidance(state, result?.context || "")
  })

  pi.on("user_python", async (event, ctx) => {
    const state = stateFor(ctx)
    const result = await evaluate("user_python", event, ctx)
    if (result === ENFORCER_CANCELLED) return
    if (result?.block) return blockedPythonResult(result.reason || "Blocked by slopgate")
    replacePendingGuidance(state, result?.context || "")
  })
}
