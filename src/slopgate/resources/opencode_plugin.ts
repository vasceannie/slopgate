/**
 * OpenCode Slopgate Plugin
 *
 * Thin TypeScript shim that bridges OpenCode's plugin system to the
 * slopgate hook engine via subprocess.
 *
 * The plugin intercepts tool.execute.before, tool.execute.after, and
 * file.edited events, listens to session lifecycle, permission, shell, and
 * command events, translates them into slopgate's canonical JSON format, and
 * applies the engine's decisions where the OpenCode event can enforce them.
 *
 * Platform limitations (vs Claude Code / Codex):
 *   - session.idle (Stop): slopgate can advise "continue" but OpenCode's
 *     plugin system has no mechanism to force continuation. Findings are
 *     logged as warnings.
 *   - permission.asked: blocking is handled at tool.execute.before; the
 *     event handler provides observability only.
 *   - No UserPromptSubmit equivalent: OpenCode doesn't expose a hook for
 *     intercepting user prompts before they're sent to the model. Rules
 *     like BUILTIN-INJECT-PROMPT are inactive on OpenCode.
 *   - file.edited is preferred for post-edit quality/lint when available.
 *     tool.execute.after receives its final input args directly on supported
 *     OpenCode versions; missing args remain unknown rather than being
 *     correlated through mutable plugin state.
 *   - permission.replied, session.compacted, session.error, session.status,
 *     shell.env, and command.executed are forwarded for replay/trace coverage;
 *     findings on those events are advisory.
 *   - transcript_path: not available from OpenCode's plugin context.
 *     Rules that read the transcript (e.g. STOP-001) operate in
 *     advisory mode without full transcript access.
 *
 * Reference: https://opencode.ai/docs/plugins/
 * Bun.spawn: https://bun.sh/docs/api/spawn
 */

/// <reference types="node" />

import { existsSync } from "node:fs"
import { dirname, join } from "node:path"

type BunResponseBody = ConstructorParameters<typeof Response>[0]

type LogLevel = "error" | "info" | "warn"

interface OpenCodeLogEntry {
  body: {
    service: string
    level: LogLevel
    message: string
  }
}

interface OpenCodeClient {
  app: {
    log(entry: OpenCodeLogEntry): Promise<void>
  }
}

interface OpenCodeEvent extends Record<string, unknown> {
  type: string
  properties?: Record<string, unknown>
  data?: Record<string, unknown>
  info?: Record<string, unknown>
}

interface OpenCodeEventEnvelope {
  event: OpenCodeEvent
}

/** Official types target: @opencode-ai/plugin@1.18.21 */
interface OpenCodePluginContext {
  client: OpenCodeClient
  project?: unknown
  directory: string
  worktree: string
  experimental_workspace?: unknown
  serverUrl?: URL
  $?: unknown
}

interface OpenCodePluginHandlers {
  "tool.execute.before": (
    input: OpenCodeToolBeforeInput,
    output: OpenCodeToolBeforeOutput,
  ) => Promise<void>
  "tool.execute.after": (
    input: OpenCodeToolAfterInput,
    output: OpenCodeToolAfterOutput,
  ) => Promise<void>
  event(input: OpenCodeEventEnvelope): Promise<void>
  tool: Record<string, OpenCodeCustomTool>
}

interface OpenCodeCustomTool {
  description: string
  args: Record<string, unknown>
  execute(args: Record<string, unknown>): Promise<string>
}

type Plugin = (
  context: OpenCodePluginContext,
  options?: Record<string, unknown>,
) => Promise<OpenCodePluginHandlers>

interface BunFileSink {
  write(data: string): number | undefined
  flush(): void | Promise<void>
  end(): void
}

interface BunSpawnResult {
  stdin: BunFileSink
  stdout: BunResponseBody
  stderr: BunResponseBody
  exited: Promise<number>
}

interface BunRuntime {
  env: Record<string, string | undefined>
  spawn(
    argv: string[],
    options: {
      env: Record<string, string | undefined>
      cwd?: string
      stdin: "pipe"
      stdout: "pipe"
      stderr: "pipe"
    },
  ): BunSpawnResult
}

declare const Bun: BunRuntime

const SLOPGATE_ARGV = Bun.env.SLOPGATE_BIN ? [Bun.env.SLOPGATE_BIN] : ["__SLOPGATE_BIN__"]
const SLOPGATE_BIN = SLOPGATE_ARGV.join(" ")
const OPENCODE_INSTALL_IDENTITY: Record<string, unknown> = {"placeholder":"__SLOPGATE_OPENCODE_IDENTITY__"}
const OPENCODE_TOOL_CONTRACT_VERSION = "slopgate-opencode-projection-v1" as const
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
}

const READ_ONLY_TOOLS = new Set(["__SLOPGATE_READ_ONLY_TOOL_IDS__"])
const KNOWN_EFFECT_TOOLS = new Set(["__SLOPGATE_EFFECTFUL_TOOL_IDS__"])
const REPAIR_MUTATION_TOOLS = new Set(["apply_patch", "edit", "write"])
const REPAIR_LINT_FLAGS = new Set(["--details", "--verbose"])
const VERIFY_TOOL = "slopgate_verify_repair"

type ExecutionOutcome = "returned" | "failed" | "blocked" | "cancelled" | "unknown"
type MutationOutcome = "committed" | "partial" | "none" | "unknown"
type EvidenceTier = "documented" | "typed" | "pinned-source" | "local-observed" | "unresolved"

interface OpenCodeToolHookInput extends Record<string, unknown> {
  tool: string
  sessionID: string
  callID: string
}

interface OpenCodeToolBeforeInput extends OpenCodeToolHookInput {}

interface OpenCodeToolBeforeOutput extends Record<string, unknown> {
  args: Record<string, unknown>
}

interface OpenCodeToolAfterInput extends OpenCodeToolHookInput {
  args: Record<string, unknown>
}

interface OpenCodeToolAfterOutput extends Record<string, unknown> {
  title: string
  output: string
  metadata: Record<string, unknown>
}

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

function mergeToolArgs(...values: unknown[]): Record<string, unknown> {
  const merged: Record<string, unknown> = {}
  for (const value of values) {
    Object.assign(merged, cloneArgs(value))
  }
  return merged
}

function ensureOutputArgs(output: OpenCodeToolBeforeOutput): Record<string, unknown> {
  if (!output.args || typeof output.args !== "object" || Array.isArray(output.args)) {
    output.args = {}
  }
  return output.args
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

function eventIdentityFields(
  event: Record<string, unknown>,
  includeBareTitle: boolean = false,
): Record<string, unknown> {
  const properties = objectValue(event, "properties")
  const data = objectValue(event, "data")
  const eventInfo = objectValue(event, "info")
  const propertiesInfo = properties ? objectValue(properties, "info") : null
  const dataInfo = data ? objectValue(data, "info") : null
  const directSources = [event, properties, data].filter(
    (source): source is Record<string, unknown> => source !== null,
  )
  const infoSources = [eventInfo, propertiesInfo, dataInfo].filter(
    (source): source is Record<string, unknown> => source !== null,
  )
  const directSessionIdKeys = [
    "opencode_session_id",
    "opencodeSessionId",
    "opencodeSessionID",
    "sessionID",
    "sessionId",
    "aggregate_id",
    "aggregateId",
  ]
  const directCallIdKeys = ["call_id", "callId", "callID", "opencode_call_id", "opencodeCallId"]
  const infoSessionIdKeys = [
    ...directSessionIdKeys,
    "id",
  ]
  const directTitleKeys = [
    "session_title",
    "sessionTitle",
    "thread_title",
    "threadTitle",
    "conversation_title",
    "conversationTitle",
  ]
  const infoTitleKeys = [
    ...directTitleKeys,
    ...(includeBareTitle ? ["title"] : []),
  ]
  const opencodeSessionId =
    directSources
      .map((source) => firstString(source, ...directSessionIdKeys))
      .find(Boolean) ||
    infoSources
      .map((source) => firstString(source, ...infoSessionIdKeys))
      .find(Boolean)
  const callId =
    directSources
      .map((source) => firstString(source, ...directCallIdKeys))
      .find(Boolean) ||
    infoSources
      .map((source) => firstString(source, ...directCallIdKeys))
      .find(Boolean)
  const title =
    directSources
      .map((source) => firstString(source, ...directTitleKeys))
      .find(Boolean) ||
    infoSources
      .map((source) => firstString(source, ...infoTitleKeys))
      .find(Boolean)

  return {
    ...(opencodeSessionId ? { session_id: opencodeSessionId } : {}),
    ...(title ? { session_title: title, session_title_source: "opencode-event" } : {}),
    ...(opencodeSessionId
      ? {
          opencode_session_id: opencodeSessionId,
          session_identity_source: "opencode-event",
        }
      : {}),
    ...(callId ? { call_id: callId } : {}),
  }
}

function eventToolArgs(event: Record<string, unknown>): Record<string, unknown> {
  const properties = objectValue(event, "properties")
  const data = objectValue(event, "data")
  return mergeToolArgs(
    event.args,
    event.arguments,
    event.input,
    event.tool_input,
    event.toolInput,
    properties,
    data,
  )
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

async function callEnforcer(
  payload: Record<string, unknown>,
  managedRepo: boolean,
): Promise<EnforcerResult | null> {
  try {
    const payloadCwd = typeof payload.cwd === "string" ? payload.cwd : undefined
    const subprocessStartedAtMs = Date.now()
    const proc = Bun.spawn(
      [...SLOPGATE_ARGV, "handle", "--platform", "opencode"],
      {
        env: Bun.env,
        cwd: payloadCwd,
        stdin: "pipe",
        stdout: "pipe",
        stderr: "pipe",
      },
    )

    // Bun.spawn with stdin:"pipe" returns a FileSink, not a WritableStream.
    // FileSink API: .write(data), .flush(), .end()
    proc.stdin.write(JSON.stringify({
      ...payload,
      slopgate_subprocess_started_at_ms: subprocessStartedAtMs,
    }))
    proc.stdin.flush()
    proc.stdin.end()

    // Read stdout and stderr as text
    const output = await new Response(proc.stdout).text()
    const stderr = await new Response(proc.stderr).text()

    const exitCode = await proc.exited

    if (exitCode !== 0) {
      console.error(`[slopgate] exit ${exitCode}: ${stderr}`)
      if (managedRepo) {
        return {
          action: "block",
          reason: "slopgate degraded mode: enforcer subprocess failed in managed repo.",
        }
      }
      return null
    }

    const trimmed = output.trim()
    // slopgate exits 0 with no stdout when no rule rendered an OpenCode action.
    // That is a clean allow/no-op, not a degraded enforcer response.
    if (!trimmed) return null

    return JSON.parse(trimmed) as EnforcerResult
  } catch (err) {
    // Catch subprocess failures, JSON parse errors, Bun API changes, etc.
    console.error(`[slopgate] callEnforcer failed: ${err}`)
    if (managedRepo) {
      return {
        action: "block",
        reason: "slopgate degraded mode: enforcer call failed in managed repo.",
      }
    }
    return null
  }
}

async function callRepairCommand(
  command: string[],
  cwd: string,
): Promise<{ exitCode: number; output: string }> {
  const proc = Bun.spawn([...SLOPGATE_ARGV, ...command], {
    env: Bun.env,
    cwd,
    stdin: "pipe",
    stdout: "pipe",
    stderr: "pipe",
  })
  proc.stdin.end()
  const output = await new Response(proc.stdout).text()
  const stderr = await new Response(proc.stderr).text()
  const exitCode = await proc.exited
  return { exitCode, output: output || stderr }
}

async function repairGateState(cwd: string): Promise<RepairGateState | null> {
  const result = await callRepairCommand(["repair", "status", "--cwd", cwd], cwd)
  if (result.exitCode !== 0 || !result.output.trim()) return null
  try {
    return JSON.parse(result.output) as RepairGateState
  } catch {
    return null
  }
}

function isExplicitRepairCommand(toolName: string, args: Record<string, unknown>): boolean {
  if (toolName.toLowerCase() === VERIFY_TOOL) return true
  if (toolName.toLowerCase() !== "bash") return false
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

function isAllowedWhileRepairRequired(
  toolName: string,
  args: Record<string, unknown>,
): boolean {
  const lowered = toolName.toLowerCase()
  return (
    READ_ONLY_TOOLS.has(lowered)
    || REPAIR_MUTATION_TOOLS.has(lowered)
    || isExplicitRepairCommand(toolName, args)
  )
}

function isKnownEffectTool(toolName: string, args: Record<string, unknown>): boolean {
  const lowered = toolName.toLowerCase()
  return (
    KNOWN_EFFECT_TOOLS.has(lowered)
    || READ_ONLY_TOOLS.has(lowered)
    || isExplicitRepairCommand(toolName, args)
  )
}

export const EnforcerPlugin: Plugin = async ({ client, directory, worktree }) => {
  const scopedDirectory = worktree || directory

  await client.app.log({
    body: {
      service: "slopgate",
      level: "info",
      message: JSON.stringify({
        event: "slopgate.plugin.loaded",
        plugin_instance_id: PLUGIN_INSTANCE_ID,
        directory,
        worktree: scopedDirectory,
        resolved_binary: SLOPGATE_BIN,
        install_identity: OPENCODE_INSTALL_IDENTITY,
      }),
    },
  })

  const managedRepo = (): boolean => findManagedRepoRoot(scopedDirectory) !== null

  const nativeIdentityFields = (
    input: Record<string, unknown>,
  ): Record<string, unknown> => {
    const sessionId =
      typeof input.sessionID === "string" && input.sessionID.trim()
        ? input.sessionID.trim()
        : firstString(input, "sessionId", "session_id")
    const callId =
      typeof input.callID === "string" && input.callID.trim()
        ? input.callID.trim()
        : firstString(input, "callId", "call_id")
    return {
      ...(sessionId ? { session_id: sessionId, opencode_session_id: sessionId } : {}),
      ...(callId ? { call_id: callId } : {}),
    }
  }

  const payloadForEvent = (
    hookEventName: string,
    toolName: string = "",
    toolInput: Record<string, unknown> = {},
    extra: Record<string, unknown> = {},
  ): Record<string, unknown> => ({
    hook_event_name: hookEventName,
    tool_name: toolName,
    tool_input: toolInput,
    cwd: scopedDirectory,
    worktree: scopedDirectory,
    opencode_tool_contract_version: OPENCODE_TOOL_CONTRACT_VERSION,
    transcript_path: null,
    ...outcomeFields("unknown", "unresolved", "unknown", "unresolved"),
    ...extra,
  })

  const logAdvisoryResult = async (
    prefix: string,
    result: EnforcerResult | null,
  ): Promise<void> => {
    if (!result) return
    const message = result.reason || result.context
    if (!message) return
    await client.app.log({
      body: {
        service: "slopgate",
        level: result.action === "block" ? "error" : "info",
        message: `[${prefix}] ${message}`,
      },
    })
  }

  const handlePostToolResult = async (
    prefix: string,
    result: EnforcerResult | null,
  ): Promise<void> => {
    if (!result) return
    if (result.action === "block") {
      throw new Error(`[${prefix}] ${result.reason || "Post-tool policy violation"}`)
    }
    if (result.action === "warn" || result.action === "context") {
      const message = result.reason || result.context
      if (message) {
        await client.app.log({
          body: {
            service: "slopgate",
            level: "warn",
            message,
          },
        })
      }
    }
  }

  return {
    // -- Pre-tool: intercept before execution ---------------------------------
    "tool.execute.before": async (input: OpenCodeToolBeforeInput, output: OpenCodeToolBeforeOutput) => {
      const outputArgs = ensureOutputArgs(output)
      const toolName = typeof input.tool === "string" ? input.tool : ""
      const pending = await repairGateState(scopedDirectory)
      if (
        managedRepo()
        && pending === null
        && toolName.toLowerCase() !== "apply_patch"
      ) {
        throw new Error("[slopgate] repair gate state is unavailable in a managed repo.")
      }
      if (
        pending?.status === "REPAIR_REQUIRED"
        && !isAllowedWhileRepairRequired(toolName, outputArgs)
      ) {
        throw new Error(
          `[slopgate] repair required for generation ${pending.generation || "unknown"}; `
          + "use read-only tools, repair, or clean verification first.",
        )
      }
      if (!isKnownEffectTool(toolName, outputArgs)) {
        throw new Error("[slopgate] unknown OpenCode tool effect; denying by default.")
      }
      const preToolArgs = cloneArgs(outputArgs)
      const payload = payloadForEvent(
        "tool.execute.before",
        toolName,
        preToolArgs,
        nativeIdentityFields(input),
      )

      const result = await callEnforcer(
        payload,
        managedRepo(),
      )
      if (!result) return

      switch (result.action) {
        case "block":
          throw new Error(`[slopgate] ${result.reason || "Blocked by policy"}`)

        case "allow":
          if (result.updated_args) {
            Object.assign(outputArgs, result.updated_args)
          }
          break

        case "context":
          if (result.context) {
            await client.app.log({
              body: {
                service: "slopgate",
                level: "info",
                message: result.context,
              },
            })
          }
          break

        default:
          break
      }
    },

    tool: {
      [VERIFY_TOOL]: {
        description: "Run clean verification and clear the matching Slopgate repair generation.",
        args: {},
        execute: async (args: Record<string, unknown>): Promise<string> => {
          const cwd = firstString(args, "cwd") || scopedDirectory
          const pending = await repairGateState(cwd)
          if (!pending?.generation) return "No repair-required generation is pending."
          const result = await callRepairCommand(
            ["repair", "verify", "--cwd", cwd, "--generation", pending.generation],
            cwd,
          )
          if (result.exitCode !== 0) {
            throw new Error(result.output.trim() || "Clean verification failed.")
          }
          return result.output.trim() || "Repair generation cleared."
        },
      },
    },

    // -- Post-tool: review after execution ------------------------------------
    "tool.execute.after": async (input: OpenCodeToolAfterInput, output: OpenCodeToolAfterOutput) => {
      const toolName = typeof input.tool === "string" ? input.tool : ""
      const postToolArgs = cloneArgs(input.args)
      const payload = payloadForEvent(
        "tool.execute.after",
        toolName,
        postToolArgs,
        {
          ...nativeIdentityFields(input),
          ...outcomeFields("returned", "pinned-source", "unknown", "unresolved"),
          tool_title: output.title,
          tool_metadata: output.metadata,
          tool_output: output.output,
          tool_result: output.output,
          tool_response: output.output,
        },
      )

      const result = await callEnforcer(
        payload,
        managedRepo(),
      )
      await handlePostToolResult("slopgate-posttool", result)
    },

    // -- Events: session lifecycle + permissions --------------------------------
    event: ({ event }: OpenCodeEventEnvelope) => (async () => {
      // -- SessionStart (session.created) ------------------------------------
      if (event.type === "session.created") {
        const payload = payloadForEvent("session.created", "", {}, eventIdentityFields(event, true))

        const result = await callEnforcer(
          payload,
          managedRepo(),
        )
        await logAdvisoryResult("session-start", result)
      }

      // -- Stop (session.idle) -----------------------------------------------
      if (event.type === "session.idle") {
        const payload = payloadForEvent("session.idle", "", {}, eventIdentityFields(event))

        const result = await callEnforcer(
          payload,
          managedRepo(),
        )
        if (!result) return

        if (result.action === "continue") {
          // Can't force continuation — log as a prominent warning
          await client.app.log({
            body: {
              service: "slopgate",
              level: "warn",
              message: `[stop-advisory] Slopgate recommends continuing: ${result.reason || "unfinished work detected"}`,
            },
          })
        } else if (result.context) {
          await client.app.log({
            body: {
              service: "slopgate",
              level: "info",
              message: `[stop] ${result.context}`,
            },
          })
        }
      }

      // -- PermissionRequest (permission.asked) -------------------------------
      if (event.type === "permission.asked") {
        const toolName = typeof event.tool === "string" ? event.tool : ""
        const toolArgs = eventToolArgs(event)

        const payload = payloadForEvent("permission.asked", toolName, toolArgs, eventIdentityFields(event))

        const result = await callEnforcer(
          payload,
          managedRepo(),
        )
        await logAdvisoryResult("permission-advisory", result)
      }

      if (event.type === "file.edited") {
        const properties = objectValue(event, "properties")
        const filePath = firstString(
          properties || {},
          "file",
          "path",
          "file_path",
          "filePath",
          "filename",
        ) || firstString(event, "path", "file_path", "filePath", "filename")
        const toolInput = eventToolArgs(event)
        if (filePath) {
          toolInput.file_path = filePath
        }
        const payload = payloadForEvent("file.edited", "Write", toolInput, {
          path: filePath,
          ...outcomeFields("unknown", "unresolved", "partial", "local-observed"),
          tool_result: event,
          tool_response: event,
          ...eventIdentityFields(event),
        })

        const result = await callEnforcer(payload, managedRepo())
        await logAdvisoryResult("slopgate-file-edited", result)
      }

      if (
        event.type === "permission.replied"
        || event.type === "session.compacted"
        || event.type === "session.error"
        || event.type === "session.status"
        || event.type === "shell.env"
        || event.type === "command.executed"
      ) {
        if (event.type === "session.compacted") {
          const pending = await repairGateState(scopedDirectory)
          if (pending?.status === "REPAIR_REQUIRED") {
            await client.app.log({
              body: {
                service: "slopgate",
                level: "warn",
                message: `[repair-required] generation ${pending.generation || "unknown"} remains pending; verify before mutating tools.`,
              },
            })
          }
        }
        const toolName = typeof event.tool === "string" ? event.tool : ""
        const payload = payloadForEvent(event.type, toolName, eventToolArgs(event), {
          tool_result: event,
          tool_response: event,
          ...eventIdentityFields(event),
        })
        const result = await callEnforcer(payload, managedRepo())
        await logAdvisoryResult(event.type, result)
      }
    })().catch(async (error: unknown) => { // no-excuse-ok: catch -- generic event boundary must never reject
      const message = error instanceof Error ? error.message : String(error)
      try {
        await client.app.log({
          body: {
            service: "slopgate",
            level: "error",
            message: `[event-advisory-failed] ${event.type}: ${message}`,
          },
        })
      } catch (logError: unknown) { // no-excuse-ok: catch -- last-resort boundary fallback
        console.error(`[slopgate] event logging failed: ${String(logError)}`)
      }
    }),
  }
}
