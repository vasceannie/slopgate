/**
 * OpenCode Vibeforcer Plugin
 *
 * Thin TypeScript shim that bridges OpenCode's plugin system to the
 * vibeforcer hook engine via subprocess.
 *
 * The plugin intercepts tool.execute.before and tool.execute.after events,
 * listens to session lifecycle and permission events, translates them into
 * vibeforcer's canonical JSON format, and applies the engine's decisions
 * (block, modify args, or allow with context).
 *
 * Platform limitations (vs Claude Code / Codex):
 *   - session.idle (Stop): vibeforcer can advise "continue" but OpenCode's
 *     plugin system has no mechanism to force continuation. Findings are
 *     logged as warnings.
 *   - permission.asked: blocking is handled at tool.execute.before; the
 *     event handler provides observability only.
 *   - No UserPromptSubmit equivalent: OpenCode doesn't expose a hook for
 *     intercepting user prompts before they're sent to the model. Rules
 *     like BUILTIN-INJECT-PROMPT are inactive on OpenCode.
 *   - tool.execute.after may omit original tool args on some OpenCode
 *     versions; this shim caches tool.execute.before args in-memory and
 *     reattaches them best-effort for post-tool backstops.
 *   - transcript_path: not available from OpenCode's plugin context.
 *     Rules that read the transcript (e.g. STOP-001) operate in
 *     advisory mode without full transcript access.
 *
 * Reference: https://opencode.ai/docs/plugins/
 * Bun.spawn: https://bun.sh/docs/api/spawn
 */

import type { Plugin } from "@opencode-ai/plugin"
import { existsSync } from "node:fs"
import { dirname } from "node:path"

const VIBEFORCER_BIN = Bun.env.VIBEFORCER_BIN || "__VIBEFORCER_BIN__"

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
    if (existsSync(`${current}/quality_gate.toml`)) {
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
      [VIBEFORCER_BIN, "handle", "--platform", "opencode"],
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
      console.error(`[vibeforcer] exit ${exitCode}: ${stderr}`)
      if (managedRepo) {
        return {
          action: "block",
          reason: "vibeforcer degraded mode: enforcer subprocess failed in managed repo.",
        }
      }
      return null
    }

    const trimmed = output.trim()
    // vibeforcer exits 0 with no stdout when no rule rendered an OpenCode action.
    // That is a clean allow/no-op, not a degraded enforcer response.
    if (!trimmed) return null

    return JSON.parse(trimmed) as EnforcerResult
  } catch (err) {
    // Catch subprocess failures, JSON parse errors, Bun API changes, etc.
    console.error(`[vibeforcer] callEnforcer failed: ${err}`)
    if (managedRepo) {
      return {
        action: "block",
        reason: "vibeforcer degraded mode: enforcer call failed in managed repo.",
      }
    }
    return null
  }
}

export const EnforcerPlugin: Plugin = async ({ project, client, $, directory, worktree }) => {
  // `directory` is set at init time. OpenCode may change CWD mid-session;
  // tool hooks receive the current CWD via their input object.
  // For event hooks (session.idle, etc.), we fall back to the init-time value.
  let currentDirectory = directory

  await client.app.log({
    body: {
      service: "vibeforcer",
      level: "info",
      message: `Vibeforcer plugin loaded (${VIBEFORCER_BIN}, session: ${SESSION_ID})`,
    },
  })

  return {
    // -- Pre-tool: intercept before execution ---------------------------------
    "tool.execute.before": async (input: any, output: any) => {
      if (input.cwd && typeof input.cwd === "string") {
        currentDirectory = input.cwd
      }

      if (!output.args || typeof output.args !== "object" || Array.isArray(output.args)) {
        output.args = {}
      }

      const preToolArgs = cloneArgs(output.args)
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
        findManagedRepoRoot(currentDirectory) !== null,
      )
      if (!result) {
        rememberToolArgs(input.tool, currentDirectory, preToolArgs)
        return
      }

      switch (result.action) {
        case "block":
          throw new Error(`[vibeforcer] ${result.reason || "Blocked by policy"}`)

        case "allow":
          if (result.updated_args) {
            Object.assign(output.args, result.updated_args)
          }
          rememberToolArgs(input.tool, currentDirectory, cloneArgs(output.args))
          break

        case "context":
          if (result.context) {
            await client.app.log({
              body: {
                service: "vibeforcer",
                level: "info",
                message: result.context,
              },
            })
          }
          rememberToolArgs(input.tool, currentDirectory, cloneArgs(output.args))
          break

        default:
          rememberToolArgs(input.tool, currentDirectory, cloneArgs(output.args))
          break
      }
    },

    // -- Post-tool: review after execution ------------------------------------
    "tool.execute.after": async (input: any, output: any) => {
      if (input.cwd && typeof input.cwd === "string") {
        currentDirectory = input.cwd
      }

      const rememberedArgs = takeRememberedToolArgs(input.tool, currentDirectory)
      const postToolArgs = { ...rememberedArgs, ...cloneArgs(output.args) }
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
        findManagedRepoRoot(currentDirectory) !== null,
      )
      if (!result) return

      if (result.action === "block") {
        throw new Error(`[vibeforcer-posttool] ${result.reason || "Post-tool policy violation"}`)
      }

      if (result.action === "warn" || result.action === "context") {
        const message = result.reason || result.context
        if (message) {
          await client.app.log({
            body: {
              service: "vibeforcer",
              level: "warn",
              message,
            },
          })
        }
      }
    },

    // -- Events: session lifecycle + permissions --------------------------------
    event: async ({ event }: { event: { type: string; [key: string]: unknown } }) => {
      // -- SessionStart (session.created) ------------------------------------
      if (event.type === "session.created") {
        const payload = {
          hook_event_name: "session.created",
          tool_name: "",
          tool_input: {},
          cwd: currentDirectory,
          session_id: SESSION_ID,
          transcript_path: null,
        }

        const result = await callEnforcer(
          payload,
          findManagedRepoRoot(currentDirectory) !== null,
        )
        if (result?.context) {
          await client.app.log({
            body: {
              service: "vibeforcer",
              level: "info",
              message: `[session-start] ${result.context}`,
            },
          })
        }
      }

      // -- Stop (session.idle) -----------------------------------------------
      if (event.type === "session.idle") {
        const payload = {
          hook_event_name: "session.idle",
          tool_name: "",
          tool_input: {},
          cwd: currentDirectory,
          session_id: SESSION_ID,
          transcript_path: null,
        }

        const result = await callEnforcer(
          payload,
          findManagedRepoRoot(currentDirectory) !== null,
        )
        if (!result) return

        if (result.action === "continue") {
          // Can't force continuation — log as a prominent warning
          await client.app.log({
            body: {
              service: "vibeforcer",
              level: "warn",
              message: `[stop-advisory] Vibeforcer recommends continuing: ${result.reason || "unfinished work detected"}`,
            },
          })
        } else if (result.context) {
          await client.app.log({
            body: {
              service: "vibeforcer",
              level: "info",
              message: `[stop] ${result.context}`,
            },
          })
        }
      }

      // -- PermissionRequest (permission.asked) -------------------------------
      if (event.type === "permission.asked") {
        const toolName = typeof event.tool === "string" ? event.tool : ""
        const toolArgs = (
          event.args && typeof event.args === "object" && !Array.isArray(event.args)
        ) ? event.args as Record<string, unknown> : {}

        const payload = {
          hook_event_name: "permission.asked",
          tool_name: toolName,
          tool_input: toolArgs,
          cwd: currentDirectory,
          session_id: SESSION_ID,
          transcript_path: null,
        }

        const result = await callEnforcer(
          payload,
          findManagedRepoRoot(currentDirectory) !== null,
        )
        if (!result) return

        if (result.action === "block") {
          await client.app.log({
            body: {
              service: "vibeforcer",
              level: "error",
              message: `[permission-advisory] Vibeforcer would deny this permission: ${result.reason}`,
            },
          })
        }
      }
    },
  }
}
