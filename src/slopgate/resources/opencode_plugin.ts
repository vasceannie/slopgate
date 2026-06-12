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
 *     tool.execute.after may omit original tool args on some OpenCode
 *     versions; this shim caches tool.execute.before args in-memory and
 *     reattaches them best-effort for post-tool backstops.
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
  cwd?: unknown
  tool?: unknown
}

interface OpenCodeEventEnvelope {
  event: OpenCodeEvent
}

interface OpenCodePluginContext {
  client: OpenCodeClient
  directory: string
}

interface OpenCodePluginHandlers {
  "tool.execute.before": (
    input: OpenCodeToolInput,
    output: OpenCodeToolOutput,
  ) => Promise<void>
  "tool.execute.after": (
    input: OpenCodeToolInput,
    output: OpenCodeToolOutput,
  ) => Promise<void>
  event(input: OpenCodeEventEnvelope): Promise<void>
}

type Plugin = (context: OpenCodePluginContext) => Promise<OpenCodePluginHandlers>

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

// Generate a unique session ID per plugin load (= per OpenCode session).
const SESSION_ID = `opencode-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`

interface EnforcerResult {
  action?: "block" | "allow" | "warn" | "context" | "continue"
  reason?: string
  context?: string
  updated_args?: Record<string, unknown>
}

interface ToolArgsCacheEntry {
  tool: string
  cwd: string
  args: Record<string, unknown>
  timestamp: number
}

interface OpenCodeToolInput extends Record<string, unknown> {
  cwd?: unknown
  tool?: unknown
}

interface OpenCodeToolOutput extends Record<string, unknown> {
  args?: Record<string, unknown>
  result?: unknown
}

const POST_TOOL_ARG_CACHE_TTL_MS = 5 * 60 * 1000
const POST_TOOL_ARG_CACHE_MAX_ENTRIES = 50
const postToolArgCache: ToolArgsCacheEntry[] = []

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

function inputToolArgs(input: Record<string, unknown>): Record<string, unknown> {
  return mergeToolArgs(
    input.args,
    input.arguments,
    input.input,
    input.tool_input,
    input.toolInput,
    cloneArgs(input.call).args,
    cloneArgs(input.call).arguments,
    cloneArgs(input.call).input,
  )
}

function outputToolArgs(output: Record<string, unknown>): Record<string, unknown> {
  return mergeToolArgs(output.args, output.arguments, output.input)
}

function ensureOutputArgs(output: OpenCodeToolOutput): Record<string, unknown> {
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

function eventToolArgs(event: Record<string, unknown>): Record<string, unknown> {
  return mergeToolArgs(
    event.args,
    event.arguments,
    event.input,
    event.tool_input,
    event.toolInput,
  )
}

function pruneToolArgCache(now: number = Date.now()): void {
  while (
    postToolArgCache.length > 0
    && now - postToolArgCache[0].timestamp > POST_TOOL_ARG_CACHE_TTL_MS
  ) {
    postToolArgCache.shift()
  }
  while (postToolArgCache.length > POST_TOOL_ARG_CACHE_MAX_ENTRIES) {
    postToolArgCache.shift()
  }
}

function rememberToolArgs(tool: unknown, cwd: string, args: Record<string, unknown>): void {
  const toolName = typeof tool === "string" ? tool : ""
  pruneToolArgCache()
  postToolArgCache.push({
    tool: toolName,
    cwd,
    args: cloneArgs(args),
    timestamp: Date.now(),
  })
  pruneToolArgCache()
}

function takeRememberedToolArgs(tool: unknown, cwd: string): Record<string, unknown> {
  const toolName = typeof tool === "string" ? tool : ""
  pruneToolArgCache()
  let index = -1
  for (let i = postToolArgCache.length - 1; i >= 0; i -= 1) {
    const entry = postToolArgCache[i]
    if (entry.tool === toolName && entry.cwd === cwd) {
      index = i
      break
    }
  }
  if (index === -1) {
    for (let i = postToolArgCache.length - 1; i >= 0; i -= 1) {
      if (postToolArgCache[i].tool === toolName) {
        index = i
        break
      }
    }
  }
  if (index === -1) return {}
  const [entry] = postToolArgCache.splice(index, 1)
  return cloneArgs(entry.args)
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
    proc.stdin.write(JSON.stringify(payload))
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

export const EnforcerPlugin: Plugin = async ({ client, directory }) => {
  // `directory` is set at init time. OpenCode may change CWD mid-session;
  // tool hooks receive the current CWD via their input object.
  // For event hooks (session.idle, etc.), we fall back to the init-time value.
  let currentDirectory = directory

  await client.app.log({
    body: {
      service: "slopgate",
      level: "info",
      message: `Slopgate plugin loaded (${SLOPGATE_BIN}, session: ${SESSION_ID})`,
    },
  })

  const managedRepo = (): boolean => findManagedRepoRoot(currentDirectory) !== null

  const payloadForEvent = (
    hookEventName: string,
    toolName: string = "",
    toolInput: Record<string, unknown> = {},
    extra: Record<string, unknown> = {},
  ): Record<string, unknown> => ({
    hook_event_name: hookEventName,
    tool_name: toolName,
    tool_input: toolInput,
    cwd: currentDirectory,
    session_id: SESSION_ID,
    transcript_path: null,
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
    "tool.execute.before": async (input: OpenCodeToolInput, output: OpenCodeToolOutput) => {
      if (input.cwd && typeof input.cwd === "string") {
        currentDirectory = input.cwd
      }

      const outputArgs = ensureOutputArgs(output)

      const preToolArgs = mergeToolArgs(inputToolArgs(input), outputToolArgs(output))
      const payload = {
        hook_event_name: "tool.execute.before",
        tool_name: input.tool,
        tool_input: preToolArgs,
        cwd: currentDirectory,
        session_id: SESSION_ID,
        transcript_path: null,
      }

      const result = await callEnforcer(
        payload,
        managedRepo(),
      )
      if (!result) {
        rememberToolArgs(input.tool, currentDirectory, preToolArgs)
        return
      }

      switch (result.action) {
        case "block":
          throw new Error(`[slopgate] ${result.reason || "Blocked by policy"}`)

        case "allow":
          if (result.updated_args) {
            Object.assign(outputArgs, result.updated_args)
          }
          rememberToolArgs(input.tool, currentDirectory, mergeToolArgs(preToolArgs, outputToolArgs(output)))
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
          rememberToolArgs(input.tool, currentDirectory, mergeToolArgs(preToolArgs, outputToolArgs(output)))
          break

        default:
          rememberToolArgs(input.tool, currentDirectory, mergeToolArgs(preToolArgs, outputToolArgs(output)))
          break
      }
    },

    // -- Post-tool: review after execution ------------------------------------
    "tool.execute.after": async (input: OpenCodeToolInput, output: OpenCodeToolOutput) => {
      if (input.cwd && typeof input.cwd === "string") {
        currentDirectory = input.cwd
      }

      const rememberedArgs = takeRememberedToolArgs(input.tool, currentDirectory)
      const postToolArgs = mergeToolArgs(
        rememberedArgs,
        inputToolArgs(input),
        outputToolArgs(output),
      )
      const payload = {
        hook_event_name: "tool.execute.after",
        tool_name: input.tool,
        tool_input: postToolArgs,
        cwd: currentDirectory,
        session_id: SESSION_ID,
        transcript_path: null,
        tool_result: output.result,
        tool_response: output.result,
      }

      const result = await callEnforcer(
        payload,
        managedRepo(),
      )
      await handlePostToolResult("slopgate-posttool", result)
    },

    // -- Events: session lifecycle + permissions --------------------------------
    event: async ({ event }: { event: { type: string; [key: string]: unknown } }) => {
      if (event.cwd && typeof event.cwd === "string") {
        currentDirectory = event.cwd
      }

      // -- SessionStart (session.created) ------------------------------------
      if (event.type === "session.created") {
        const payload = payloadForEvent("session.created")

        const result = await callEnforcer(
          payload,
          managedRepo(),
        )
        await logAdvisoryResult("session-start", result)
      }

      // -- Stop (session.idle) -----------------------------------------------
      if (event.type === "session.idle") {
        const payload = payloadForEvent("session.idle")

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

        const payload = payloadForEvent("permission.asked", toolName, toolArgs)

        const result = await callEnforcer(
          payload,
          managedRepo(),
        )
        await logAdvisoryResult("permission-advisory", result)
      }

      if (event.type === "file.edited") {
        const filePath = firstString(
          event,
          "path",
          "file_path",
          "filePath",
          "filename",
        )
        const toolInput = eventToolArgs(event)
        if (filePath) {
          toolInput.file_path = filePath
        }
        const payload = payloadForEvent("file.edited", "Write", toolInput, {
          path: filePath,
          tool_result: event,
          tool_response: event,
        })

        const result = await callEnforcer(payload, managedRepo())
        await handlePostToolResult("slopgate-file-edited", result)
      }

      if (
        event.type === "permission.replied"
        || event.type === "session.compacted"
        || event.type === "session.error"
        || event.type === "session.status"
        || event.type === "shell.env"
        || event.type === "command.executed"
      ) {
        const toolName = typeof event.tool === "string" ? event.tool : ""
        const payload = payloadForEvent(event.type, toolName, eventToolArgs(event), {
          tool_result: event,
          tool_response: event,
        })
        const result = await callEnforcer(payload, managedRepo())
        await logAdvisoryResult(event.type, result)
      }
    },
  }
}
