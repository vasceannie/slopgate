/**
 * OpenCode Slopgate Plugin — @opencode/plugin@2.2.5.
 *
 * V2-only server plugin. Blocking decisions belong to execute.before, and to
 * permission.evaluate for a Code Mode program's fetch, which no tool hook sees.
 * execute.after and the public event stream report detection, not prevention.
 * Session locations, not the plugin instance's location, scope enforcement.
 * Stop findings remain advisory; no experimental continuation hooks are used.
 *
 * https://opencode.ai/v2/docs/build/plugins/migrate-v1/
 */

/// <reference types="node" />

import { type ChildProcess, spawn } from "node:child_process"
import { existsSync, readFileSync } from "node:fs"
import { dirname, join } from "node:path"
import { Plugin } from "@opencode/plugin"
import { Error as ToolError, type Result as ToolResult } from "@opencode/plugin/promise/tool"
import type { Session } from "@opencode/schema/session"

type ToolHookEvent = Parameters<Parameters<Plugin.Context["tool"]["hook"]>[1]>[0]
type ToolBeforeEvent = Exclude<ToolHookEvent, { status: string }>
type ToolAfterEvent = Extract<ToolHookEvent, { status: string }>
type PermissionEvaluation = Parameters<Parameters<Plugin.Context["permission"]["hook"]>[1]>[0]


declare const Bun: { env: Record<string, string | undefined> }

const SLOPGATE_ARGV = Bun.env.SLOPGATE_BIN ? [Bun.env.SLOPGATE_BIN] : ["__SLOPGATE_BIN__"]
const SLOPGATE_BIN = SLOPGATE_ARGV.join(" ")
const OPENCODE_INSTALL_IDENTITY: Record<string, unknown> = {"placeholder":"__SLOPGATE_OPENCODE_IDENTITY__"}
const OPENCODE_TOOL_CONTRACT_VERSION = "slopgate-opencode-projection-v2" as const
const PLUGIN_INSTANCE_ID = crypto.randomUUID()

interface EnforcerResult {
  action?: "block" | "allow" | "warn" | "context" | "continue"
  reason?: string
  context?: string
  updated_args?: Record<string, unknown>
}

interface RepairGateState {
  status: string
  generation?: string
  reason?: string
  targets?: unknown
  worktree?: unknown
}

type RepairCommandStatus = "ok" | "timeout" | "failed" | "cancelled"

interface RepairCommandResult {
  exitCode: number
  output: string
  status: RepairCommandStatus
}

const READ_ONLY_TOOLS = new Set(["__SLOPGATE_READ_ONLY_TOOL_IDS__"])
const KNOWN_EFFECT_TOOLS = new Set(["__SLOPGATE_EFFECTFUL_TOOL_IDS__"])
const REPAIR_MUTATION_TOOLS: Record<string, true> = { patch: true, edit: true, write: true }
const SHELL_TOOLS: Record<string, true> = { shell: true, bash: true }
const REPAIR_LINT_FLAGS = new Set(["--details", "--verbose"])
const READ_ONLY_BASH_COMMANDS = new Set([
  "cat",
  "cd",
  "echo",
  "file",
  "find",
  "grep",
  "head",
  "jq",
  "ls",
  "nl",
  "pwd",
  "readlink",
  "realpath",
  "rg",
  "sed",
  "stat",
  "tail",
  "wc",
  "which",
])
const READ_ONLY_GIT_SUBCOMMANDS = new Set([
  "branch",
  "check-ignore",
  "describe",
  "diff",
  "log",
  "ls-files",
  "remote",
  "rev-parse",
  "show",
  "status",
])
const SHELL_MUTATION_MARKERS = /(?:&&|\|\||[;|<>]|\$\([^)]*\)|`[^`]*`)/
const VERIFY_TOOL = "slopgate_verify_repair"
// The host re-enters execute.before for every tool an execute program calls, so
// the outer call adds no file access of its own and inner calls stay gated. The
// program's fetch has no tool hook, so evaluatePermission gates it instead.
const CODE_MODE_TOOL = "execute"
// Host fetch asserts the same permission as the webfetch tool.
const FETCH_PERMISSION = "webfetch"
const DEFAULT_REPAIR_TIMEOUT_MS = 60_000
const DEFAULT_ENFORCER_TIMEOUT_MS = 10_000
const verifyFlights = new Map<string, Promise<RepairCommandResult>>()
// Host fetch names its execute call as the permission source, the only thing
// separating it from the direct webfetch tool.
const runningCodeModeCalls = new Set<string>()

// V2 tool IDs are exact: Read and read would be different tools.
function nativeToolId(toolName: string): string {
  return toolName.trim()
}

function nativeMutationToolId(toolName: string): string | null {
  const normalized = nativeToolId(toolName)
  return Object.hasOwn(REPAIR_MUTATION_TOOLS, normalized) ? normalized : null
}

type ExecutionOutcome = "returned" | "failed" | "blocked" | "cancelled" | "unknown"
type MutationOutcome = "committed" | "partial" | "none" | "unknown"
type EvidenceTier = "documented" | "typed" | "pinned-source" | "local-observed" | "unresolved"


function outcomeFields(
  executionOutcome: ExecutionOutcome,
  executionEvidenceTier: EvidenceTier,
  mutationOutcome: MutationOutcome,
  mutationEvidenceTier: EvidenceTier,
): Record<string, unknown> {
  return {
    execution_outcome: executionOutcome,
    mutation_outcome: mutationOutcome,
    evidence_tier: {
      execution: executionEvidenceTier,
      mutation: mutationEvidenceTier,
    },
  }
}

function cloneArgs(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return {}
  }
  try {
    return JSON.parse(JSON.stringify(value)) as Record<string, unknown>
  } catch {
    return { ...(value as Record<string, unknown>) }
  }
}


function firstString(value: Record<string, unknown>, ...keys: string[]): string {
  for (const key of keys) {
    const candidate = value[key]
    if (typeof candidate === "string" && candidate.trim()) {
      return candidate.trim()
    }
  }
  return ""
}

function objectValue(
  value: Record<string, unknown>,
  key: string,
): Record<string, unknown> | null {
  const candidate = value[key]
  if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)) {
    return null
  }
  return Object.fromEntries(Object.entries(candidate))
}

function logDecision(level: "info" | "warn" | "error", event: string, message: string): void {
  console[level](JSON.stringify({ service: "slopgate", event, message }))
}

function nativeIdentityFields(event: { sessionID: string; id: string }): Record<string, unknown> {
  return {
    session_id: event.sessionID,
    opencode_session_id: event.sessionID,
    call_id: event.id,
    session_identity_source: "opencode-v2",
  }
}

interface SessionScope {
  directory: string
  worktree: string
}

function scopeForDirectory(ctx: Plugin.Context, directory: string): SessionScope {
  const project = ctx.location.project.directory
  // A non-git location reports the filesystem root as its project.
  const usable = directory === ctx.location.directory && dirname(project) !== project
  return { directory, worktree: usable ? project : directory }
}

async function sessionScope(ctx: Plugin.Context, sessionID: Session.ID): Promise<SessionScope> {
  const session = await ctx.session.get({ sessionID })
  return scopeForDirectory(ctx, session.location.directory)
}

function payloadForEvent(
  hookEventName: string,
  scope: SessionScope,
  fields: Record<string, unknown>,
): Record<string, unknown> {
  return {
    hook_event_name: hookEventName,
    cwd: scope.directory,
    worktree: scope.worktree,
    opencode_tool_contract_version: OPENCODE_TOOL_CONTRACT_VERSION,
    transcript_path: null,
    ...outcomeFields("unknown", "unresolved", "unknown", "unresolved"),
    ...fields,
  }
}

function logAdvisoryResult(prefix: string, result: EnforcerResult | null): void {
  const message = result?.reason || result?.context
  if (message) logDecision(result?.action === "block" ? "warn" : "info", prefix, message)
}

async function beforeTool(ctx: Plugin.Context, event: ToolBeforeEvent): Promise<void> {
  const scope = await sessionScope(ctx, event.sessionID)
  const args = cloneArgs(event.input)
  const mode = enforcementModeFor(scope.directory)
  const strictRepo = mode === "repo_strict"
  const pending = strictRepo ? await repairGateState(scope.directory, scope.worktree) : null
  const unavailable = strictRepo && pending === null
  if (unavailable && !isAllowedWhenRepairStateUnavailable(event.tool, args)) {
    throw new ToolError({ message: "[slopgate] repair gate state is unavailable in a managed repo." })
  }
  if (pending?.status === "REPAIR_REQUIRED" && !isAllowedWhileRepairRequired(event.tool, args)) {
    throw new ToolError({
      message: `[slopgate] ${repairRecoveryProtocol(pending.generation || "unknown", pending.targets)}`,
    })
  }
  const result = await callEnforcer(payloadForEvent("tool.execute.before", scope, {
    tool_name: event.tool,
    tool_input: args,
    ...nativeIdentityFields(event),
  }), mode !== "outside_repo", unavailable)
  logDecision("info", "slopgate.tool.evaluated", JSON.stringify({
    session_id: event.sessionID, call_id: event.id, action: result?.action || "allow",
    reason: result?.reason || "",
  }))
  if (result?.action === "block") {
    throw new ToolError({ message: `[slopgate] ${result.reason || "Blocked by policy"}` })
  }
  if (!isKnownEffectTool(event.tool, args)) {
    logDecision("warn", "slopgate-tool-scope", `[scope=${mode}] unknown OpenCode tool allowed; global safety rules still apply.`)
  }
  if (result?.action === "allow" && result.updated_args) {
    event.input = { ...args, ...result.updated_args }
  }
  if (result?.context) logDecision("info", "slopgate-pretool", result.context)
  if (nativeToolId(event.tool) === CODE_MODE_TOOL) runningCodeModeCalls.add(event.id)
}

async function codeModeFetchDenial(ctx: Plugin.Context, sessionID: Session.ID): Promise<string | null> {
  const unavailable = "[slopgate] fetch is denied: repair gate state is unavailable in a managed repo."
  try {
    const scope = await sessionScope(ctx, sessionID)
    if (enforcementModeFor(scope.directory) !== "repo_strict") return null
    const pending = await repairGateState(scope.directory, scope.worktree)
    if (pending === null) return unavailable
    if (pending.status !== "REPAIR_REQUIRED") return null
    return `[slopgate] fetch is denied during repair. ${repairRecoveryProtocol(pending.generation || "unknown", pending.targets)}`
  } catch (error: unknown) {
    logDecision("error", "code-mode-fetch-gate-failed", String(error))
    return unavailable
  }
}

async function evaluatePermission(ctx: Plugin.Context, event: PermissionEvaluation): Promise<void> {
  if (event.action !== FETCH_PERMISSION) return
  if (!event.source || !runningCodeModeCalls.has(event.source.id)) return
  // Read per request: a program can outlive the state it started under.
  const denial = await codeModeFetchDenial(ctx, event.sessionID)
  if (denial === null) return
  event.effect = "deny"
  event.message = denial
}

function withNotice(result: ToolResult, notice: string): ToolResult {
  const { content, output } = result
  const original = typeof content === "string"
    ? [{ type: "text" as const, text: content }]
    : content?.length
      ? content
      : output === undefined
        ? []
        : [{ type: "text" as const, text: typeof output === "string" ? output : JSON.stringify(output) ?? String(output) }]
  return { ...result, content: [...original, { type: "text" as const, text: notice }] }
}

function postToolNotice(reason: string, pending: RepairGateState | null): string {
  const notice = `[slopgate] This tool call already ran and was not rolled back, but a post-tool check failed: ${reason}`
  if (pending?.status !== "REPAIR_REQUIRED") return notice
  return `${notice} Repair generation ${pending.generation || "unknown"} is now required. ${repairRecoverySteps(pending.targets)}`
}

// A thrown after-hook cannot reject the call, so the result is the model's only signal.
async function tellModelAboutPostToolBlock(event: ToolAfterEvent, reason: string, scope: SessionScope): Promise<void> {
  const notice = postToolNotice(reason, await repairGateState(scope.directory, scope.worktree))
  if (event.status === "completed") {
    event.result = withNotice(event.result, notice)
    return
  }
  event.error = new ToolError({
    message: `${event.error.message}\n\n${notice}`,
    error: event.error.error,
    metadata: event.error.metadata,
  })
}

async function afterTool(ctx: Plugin.Context, event: ToolAfterEvent): Promise<void> {
  // Inner tools share the execute call's ID, so only its own completion ends gating.
  if (nativeToolId(event.tool) === CODE_MODE_TOOL) runningCodeModeCalls.delete(event.id)
  try {
    const scope = await sessionScope(ctx, event.sessionID)
    const completed = event.status === "completed"
    const resultFields = completed
      ? {
          tool_metadata: event.result.metadata,
          tool_output: event.result.content,
          tool_result: event.result,
          tool_response: event.result,
        }
      : { tool_error: event.error.message, tool_result: { error: event.error.message } }
    const result = await callEnforcer(payloadForEvent("tool.execute.after", scope, {
      tool_name: event.tool,
      tool_input: cloneArgs(event.input),
      ...nativeIdentityFields(event),
      ...outcomeFields(completed ? "returned" : "failed", "typed", "unknown", "unresolved"),
      ...resultFields,
    }), findManagedRepoRoot(scope.directory) !== null)
    const detail = result?.reason || result?.context
    if (detail) {
      logDecision("warn", "slopgate-posttool",
        `post-tool detection only: execution already ${completed ? "completed" : "failed"}; `
        + "no prevention or rollback occurred. " + detail
        + (result?.action === "block" ? " Repair is required before the next mutation." : ""))
    }
    if (result?.action === "block") {
      await tellModelAboutPostToolBlock(event, result.reason || "Blocked by policy", scope)
    }
  } catch (error: unknown) {
    logDecision("error", "post-tool-advisory-failed", String(error))
  }
}

const OBSERVED_EVENTS = [
  "session.created", "session.idle", "session.status", "session.execution.failed",
  "session.compaction.ended", "permission.asked", "permission.replied",
] as const

async function observeEvents(ctx: Plugin.Context, signal: AbortSignal): Promise<void> {
  try {
    for await (const event of ctx.event.subscribe({ types: [...OBSERVED_EVENTS], signal })) {
      try {
        const directory = event.location?.directory
        // Events without a location cannot safely be attributed to this instance.
        if (!directory || directory !== ctx.location.directory) continue
        const data = event.data as Record<string, unknown>
        const sessionId = firstString(data, "sessionID")
        const result = await callEnforcer(payloadForEvent(event.type, scopeForDirectory(ctx, directory), {
          tool_name: "",
          tool_input: {},
          session_id: sessionId,
          opencode_session_id: sessionId,
          ...(event.type === "session.created" && typeof data.title === "string"
            ? { session_title: data.title, session_title_source: "opencode-event" } : {}),
          tool_result: event,
          tool_response: event,
        }), findManagedRepoRoot(directory) !== null)
        if (result?.action === "continue") {
          logDecision("warn", "stop-advisory", `Slopgate recommends continuing: ${result.reason || "unfinished work detected"}`)
        } else {
          logAdvisoryResult(event.type, result)
        }
      } catch (error: unknown) {
        logDecision("error", "event-advisory-failed", `${event.type}: ${String(error)}`)
      }
    }
  } catch (error: unknown) {
    if (!signal.aborted) logDecision("error", "event-stream-failed", String(error))
  }
}

function findManagedRepoRoot(start: string): string | null {
  let current = start
  while (true) {
    if (existsSync(join(current, "slopgate.toml"))) {
      return current
    }
    const parent = dirname(current)
    if (parent === current) return null
    current = parent
  }
}

type EnforcementMode = "outside_repo" | "repo_strict" | "repo_relaxed"

const DISABLE_SENTINELS = [".noslopgate", ".no-slop-gate"] as const

function tomlDisablesRepo(content: string): boolean {
  let section = ""
  for (const line of content.split(/\r?\n/)) {
    const header = line.match(/^\s*\[([^\]]+)\]\s*(?:#.*)?$/)
    if (header) {
      section = header[1] || ""
      continue
    }
    if (
      section === "slopgate"
      && /^\s*enabled\s*=\s*false(?:\s*#.*)?$/i.test(line)
    ) {
      return true
    }
  }
  return false
}

function enforcementModeFor(start: string): EnforcementMode {
  const root = findManagedRepoRoot(start)
  if (!root) return "outside_repo"
  if (DISABLE_SENTINELS.some((sentinel) => existsSync(join(root, sentinel)))) {
    return "repo_relaxed"
  }
  try {
    const content = readFileSync(join(root, "slopgate.toml"), "utf8")
    return tomlDisablesRepo(content) ? "repo_relaxed" : "repo_strict"
  } catch {
    return "repo_strict"
  }
}

function enforcerFailureResult(
  payload: Record<string, unknown>,
  managedRepo: boolean,
  repairStatusUnavailable: boolean,
  reason: string,
): EnforcerResult | null {
  if (!managedRepo) return null
  const toolName = typeof payload.tool_name === "string" ? payload.tool_name : ""
  const toolInput = objectValue(payload, "tool_input") ?? {}
  if (isReadOnlyTool(toolName)) return null
  if (repairStatusUnavailable && isAllowedWhenRepairStateUnavailable(toolName, toolInput)) return null
  return { action: "block", reason }
}

function parseEnforcerOutput(output: string): EnforcerResult | null {
  const trimmed = output.trim()
  // A clean hook exits 0 with no stdout; treat that as a successful no-op.
  if (!trimmed) return null
  return JSON.parse(trimmed) as EnforcerResult
}

async function callEnforcer(
  payload: Record<string, unknown>,
  managedRepo: boolean,
  repairStatusUnavailable: boolean = false,
): Promise<EnforcerResult | null> {
  const payloadCwd = typeof payload.cwd === "string" ? payload.cwd : undefined
  const rawTimeout = Bun.env.SLOPGATE_ENFORCER_TIMEOUT_MS
  const parsedTimeout = rawTimeout === undefined ? DEFAULT_ENFORCER_TIMEOUT_MS : Number(rawTimeout)
  const timeoutMs = Number.isFinite(parsedTimeout) && parsedTimeout > 0
    ? parsedTimeout
    : DEFAULT_ENFORCER_TIMEOUT_MS
  const subprocessStartedAtMs = Date.now()

  return new Promise((resolve) => {
    let child: ChildProcess | undefined
    let settled = false
    let stdout = ""
    let stderr = ""
    let timer: ReturnType<typeof setTimeout>
    const finish = (result: EnforcerResult | null): void => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      resolve(result)
    }
    timer = setTimeout(() => {
      if (settled) return
      settled = true
      console.error(`[slopgate] enforcer subprocess timed out after ${timeoutMs}ms`)
      const result = enforcerFailureResult(
        payload,
        managedRepo,
        repairStatusUnavailable,
        "slopgate degraded mode: enforcer subprocess timed out in managed repo.",
      )
      if (child) {
        // Reap the killed child before the host can exit on the timeout result.
        child.once("close", () => resolve(result))
        child.stdin?.destroy()
        child.stdout?.destroy()
        child.stderr?.destroy()
        killProcessGroup(child)
      } else {
        resolve(result)
      }
    }, timeoutMs)
    try {
      const argv = [...SLOPGATE_ARGV, "handle", "--platform", "opencode"]
      child = spawn(
        argv[0],
        argv.slice(1),
        {
          cwd: payloadCwd,
          env: process.env,
          detached: process.platform !== "win32",
          stdio: ["pipe", "pipe", "pipe"],
        },
      )
      child.stdout?.on("data", (chunk: Buffer | string) => {
        stdout += chunk.toString()
      })
      child.stderr?.on("data", (chunk: Buffer | string) => {
        stderr += chunk.toString()
      })
      child.on("error", (err: Error) => {
        console.error(`[slopgate] callEnforcer failed: ${err}`)
        finish(enforcerFailureResult(
          payload,
          managedRepo,
          repairStatusUnavailable,
          "slopgate degraded mode: enforcer call failed in managed repo.",
        ))
      })
      child.on("close", (exitCode: number | null) => {
        if (settled) return
        if (exitCode !== 0) {
          console.error(`[slopgate] exit ${exitCode ?? 1}: ${stderr}`)
          finish(enforcerFailureResult(
            payload,
            managedRepo,
            repairStatusUnavailable,
            "slopgate degraded mode: enforcer subprocess failed in managed repo.",
          ))
          return
        }
        try {
          finish(parseEnforcerOutput(stdout))
        } catch (err) {
          console.error(`[slopgate] callEnforcer failed: ${err}`)
          finish(enforcerFailureResult(
            payload,
            managedRepo,
            repairStatusUnavailable,
            "slopgate degraded mode: enforcer call failed in managed repo.",
          ))
        }
      })
      child.stdin?.end(JSON.stringify({
        ...payload,
        slopgate_subprocess_started_at_ms: subprocessStartedAtMs,
      }))
    } catch (err) {
      console.error(`[slopgate] callEnforcer failed: ${err}`)
      finish(enforcerFailureResult(
        payload,
        managedRepo,
        repairStatusUnavailable,
        "slopgate degraded mode: enforcer call failed in managed repo.",
      ))
    }
  })
}

function repairTimeoutMs(): number {
  const raw = Bun.env.SLOPGATE_REPAIR_VERIFY_TIMEOUT_MS
  const parsed = raw === undefined ? DEFAULT_REPAIR_TIMEOUT_MS : Number(raw)
  return Number.isFinite(parsed) && parsed > 0 ? parsed : DEFAULT_REPAIR_TIMEOUT_MS
}

function killProcessGroup(child: ChildProcess): void {
  const pid = child.pid
  if (pid == null) return
  if (process.platform === "win32") {
    spawn("taskkill", ["/PID", String(pid), "/T", "/F"])
    child.kill("SIGKILL")
    return
  }
  try {
    process.kill(-pid, "SIGKILL")
  } catch {
    child.kill("SIGKILL")
  }
}

function callRepairCommand(
  command: string[],
  cwd: string,
  options?: { timeoutMs?: number; signal?: AbortSignal },
): Promise<RepairCommandResult> {
  return new Promise((resolve) => {
    const child = spawn(SLOPGATE_ARGV[0], [...SLOPGATE_ARGV.slice(1), ...command], {
      cwd,
      env: process.env,
      stdio: ["ignore", "pipe", "pipe"],
      detached: process.platform !== "win32",
    })
    let stdout = ""
    let stderr = ""
    let settled = false
    const finish = (result: RepairCommandResult) => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      signal?.removeEventListener("abort", onAbort)
      resolve(result)
    }
    const signal = options?.signal
    const onAbort = () => {
      killProcessGroup(child)
      finish({
        exitCode: 1,
        output: JSON.stringify({ status: "cancelled" }),
        status: "cancelled",
      })
    }
    const timer = setTimeout(() => {
      killProcessGroup(child)
      finish({
        exitCode: 1,
        output: JSON.stringify({ status: "timeout" }),
        status: "timeout",
      })
    }, options?.timeoutMs ?? repairTimeoutMs())
    if (signal?.aborted) {
      onAbort()
      return
    }
    signal?.addEventListener("abort", onAbort, { once: true })
    child.stdout?.on("data", (chunk: Buffer | string) => {
      stdout += chunk.toString()
    })
    child.stderr?.on("data", (chunk: Buffer | string) => {
      stderr += chunk.toString()
    })
    child.on("error", (err: Error) => {
      finish({
        exitCode: 1,
        output: JSON.stringify({ status: "failed", reason: String(err) }),
        status: "failed",
      })
    })
    child.on("close", (code: number | null) => {
      if (settled) return
      const exitCode = code ?? 1
      finish({
        exitCode,
        output: stdout || stderr,
        status: exitCode === 0 ? "ok" : "failed",
      })
    })
  })
}

function verifyRepairFlight(
  cwd: string,
  worktree: string,
  generation: string,
): Promise<RepairCommandResult> {
  const key = `${worktree}::${cwd}::${generation}`
  const existing = verifyFlights.get(key)
  if (existing) return existing
  const pending = callRepairCommand(
    [
      "repair", "verify", "--cwd", cwd,
      "--worktree", worktree, "--generation", generation,
    ],
    cwd,
  ).finally(() => {
    verifyFlights.delete(key)
  })
  verifyFlights.set(key, pending)
  return pending
}

async function repairGateState(
  cwd: string,
  worktree: string,
): Promise<RepairGateState | null> {
  const result = await callRepairCommand(
    ["repair", "status", "--cwd", cwd, "--worktree", worktree],
    cwd,
  )
  if (result.exitCode !== 0 || !result.output.trim()) return null
  try {
    return JSON.parse(result.output) as RepairGateState
  } catch {
    return null
  }
}

function firstCausalLabel(targets: unknown): string {
  if (!Array.isArray(targets) || targets.length === 0) {
    return "invalid or legacy repair state"
  }
  const target = targets[0]
  if (typeof target !== "object" || target === null || Array.isArray(target)) {
    return "invalid or legacy repair state"
  }
  const record = target as Record<string, unknown>
  const rule = typeof record.rule_id === "string" ? record.rule_id : ""
  const path = typeof record.path === "string" ? record.path : ""
  if (rule && path) return `${rule} in ${path}`
  if (rule) return `rule ${rule}`
  if (path) return `file ${path}`
  return "invalid or legacy repair state"
}

function repairRecoveryProtocol(
  generation: string,
  targets: unknown,
): string {
  return (
    `STOP: do not retry this blocked mutation; equivalent retries remain blocked `
    + `until generation ${generation} clears. ${repairRecoverySteps(targets)}`
  )
}

function repairRecoverySteps(targets: unknown): string {
  return (
    "Recovery protocol: "
    + `(1) read the first causal finding: ${firstCausalLabel(targets)}; `
    + "(2) inspect affected files with declared read-only tools; "
    + "(3) make one focused repair with an allowed mutation tool "
    + "(write, edit, patch); "
    + "(4) run slopgate_verify_repair; it resolves the pending generation from repair state "
    + "and clears it only after clean verification. Allowed during repair: declared read-only "
    + "tools, write/edit/patch, slopgate_verify_repair, Code Mode execute (each tool it "
    + "calls is gated and its fetch is denied), exact slopgate lint check; "
    + "compound shell, diagnostic, and wrapper-tool retries remain blocked."
  )
}

function isReadOnlyTool(toolName: string): boolean {
  return READ_ONLY_TOOLS.has(nativeToolId(toolName))
}

function isExplicitRepairCommand(toolName: string, args: Record<string, unknown>): boolean {
  const normalized = nativeToolId(toolName)
  if (normalized === VERIFY_TOOL) return true
  if (!Object.hasOwn(SHELL_TOOLS, normalized)) return false
  const command = firstString(args, "command", "cmd", "script")
  const tokens = command.trim().split(/\s+/)
  return (
    tokens.length >= 3
    && tokens[0] === "slopgate"
    && tokens[1] === "lint"
    && tokens[2] === "check"
    && tokens.slice(3).every((token) => REPAIR_LINT_FLAGS.has(token))
  )
}

function isReadOnlyBashCommand(args: Record<string, unknown>): boolean {
  const command = firstString(args, "command", "cmd", "script")
  if (!command || SHELL_MUTATION_MARKERS.test(command)) return false
  const tokens = command.split(/\s+/)
  const executable = tokens[0]?.split("/").pop() || ""
  if (READ_ONLY_BASH_COMMANDS.has(executable)) return true
  if (executable !== "git") return false
  const subcommand = tokens.slice(1).find((token) => !token.startsWith("-"))
  return READ_ONLY_GIT_SUBCOMMANDS.has(subcommand || "")
}

function isAllowedWhileRepairRequired(
  toolName: string,
  args: Record<string, unknown>,
): boolean {
  return (
    isReadOnlyTool(toolName)
    || nativeToolId(toolName) === CODE_MODE_TOOL
    || (Object.hasOwn(SHELL_TOOLS, nativeToolId(toolName)) && isReadOnlyBashCommand(args))
    || nativeMutationToolId(toolName) !== null
    || isExplicitRepairCommand(toolName, args)
  )
}

function isAllowedWhenRepairStateUnavailable(
  toolName: string,
  args: Record<string, unknown>,
): boolean {
  return (
    isReadOnlyTool(toolName)
    || nativeToolId(toolName) === CODE_MODE_TOOL
    || nativeMutationToolId(toolName) === "patch"
    || isExplicitRepairCommand(toolName, args)
  )
}

function isKnownEffectTool(toolName: string, args: Record<string, unknown>): boolean {
  const toolId = nativeToolId(toolName)
  return (
    KNOWN_EFFECT_TOOLS.has(toolId)
    || READ_ONLY_TOOLS.has(toolId)
    || isExplicitRepairCommand(toolName, args)
  )
}

export default Plugin.define({
  id: "slopgate",
  async setup(ctx) {
    logDecision("info", "slopgate.plugin.loaded", JSON.stringify({
      plugin_instance_id: PLUGIN_INSTANCE_ID,
      directory: ctx.location.directory,
      opencode_version: ctx.app.version,
      resolved_binary: SLOPGATE_BIN,
      install_identity: OPENCODE_INSTALL_IDENTITY,
    }))
    await ctx.tool.hook("execute.before", (event) => beforeTool(ctx, event))
    await ctx.tool.hook("execute.after", (event) => afterTool(ctx, event))
    await ctx.permission.hook("evaluate", (event) => evaluatePermission(ctx, event))
    await ctx.tool.transform((editor) => {
      editor.add({
        name: VERIFY_TOOL,
        description: "Run clean verification and clear the matching Slopgate repair generation.",
        input: { type: "object", properties: {}, additionalProperties: false },
        // Code Mode tools are only reachable through execute; repair must stay directly callable.
        options: { codemode: false },
        async execute(_input, context) {
          const { directory, worktree } = await sessionScope(ctx, context.sessionID)
          const pending = await repairGateState(directory, worktree)
          if (!pending?.generation) return { content: "No repair-required generation is pending." }
          // A verifier is shared across sessions; one caller cannot cancel its peers.
          const result = await verifyRepairFlight(directory, worktree, pending.generation)
          if (result.status !== "ok" || result.exitCode !== 0) {
            throw new ToolError({ message: result.output.trim() || JSON.stringify({ status: result.status }) })
          }
          return { content: result.output.trim() || "Repair generation cleared." }
        },
      })
    })
    const controller = new AbortController()
    const observing = observeEvents(ctx, controller.signal)
    return async () => {
      controller.abort()
      await observing
    }
  },
})
