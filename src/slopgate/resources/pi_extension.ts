/**
 * Pi Slopgate Extension
 *
 * Bridges Pi extension events to `slopgate handle --platform pi`.
 *
 * Reference: https://pi.dev/docs/latest/extensions
 */

interface NodeReadableLike {
  on(eventName: "data", handler: (chunk: string | Uint8Array) => void): void
}

interface NodeWritableLike {
  end(): void
  write(data: string): void
}

interface NodeChildProcessLike {
  stderr: NodeReadableLike
  stdin: NodeWritableLike
  stdout: NodeReadableLike
  on(eventName: "close", handler: (code: number | null) => void): void
  on(eventName: "error", handler: (error: Error) => void): void
}

interface NodeProcessLike {
  cwd(): string
  env: Record<string, string | undefined>
}

// @ts-ignore Pi provides Node built-ins at runtime; this standalone template avoids @types/node.
import { spawn } from "node:child_process"
// @ts-ignore Pi provides Node built-ins at runtime; this standalone template avoids @types/node.
import { existsSync } from "node:fs"
// @ts-ignore Pi provides Node built-ins at runtime; this standalone template avoids @types/node.
import { dirname, join } from "node:path"
// @ts-ignore Pi provides Node built-ins at runtime; this standalone template avoids @types/node.
import runtimeProcessValue from "node:process"

const runtimeProcess = runtimeProcessValue as NodeProcessLike

const SLOPGATE_ARGV = runtimeProcess.env.SLOPGATE_BIN ? [runtimeProcess.env.SLOPGATE_BIN] : ["__SLOPGATE_BIN__"]
const SESSION_ID = `pi-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`

type PiEventName =
  | "agent_end"
  | "before_agent_start"
  | "input"
  | "tool_call"
  | "tool_execution_end"
  | "tool_result"
  | "turn_end"

interface PiEnforcerResult {
  block?: boolean
  reason?: string
  context?: string
  updated_input?: Record<string, unknown>
}

interface PiEventLike {
  toolName?: string
  toolCallId?: string
  input?: Record<string, unknown>
  args?: Record<string, unknown>
  content?: unknown
  details?: unknown
  isError?: boolean
  prompt?: string
  text?: string
  images?: unknown[]
  message?: unknown
  result?: unknown
  reason?: string
  systemPrompt?: string
}

interface PiContextLike {
  cwd?: string
  ui?: {
    notify?(message: string, level?: "info" | "warn" | "error"): void
  }
}

interface PiHookResult {
  action?: "continue" | "handled" | "transform"
  block?: boolean
  content?: unknown
  details?: unknown
  images?: unknown[]
  isError?: boolean
  message?: Record<string, unknown>
  reason?: string
  systemPrompt?: string
  text?: string
}

type PiEventHandler = (
  event: PiEventLike,
  ctx: PiContextLike,
) => Promise<PiHookResult | void> | PiHookResult | void

interface PiExtensionAPI {
  on(eventName: PiEventName, handler: PiEventHandler): void
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
  return event.input || event.args || {}
}

function promptFromEvent(event: PiEventLike): string {
  return event.text || event.prompt || ""
}

function toolResultFromEvent(event: PiEventLike): unknown {
  return event.content ?? event.result ?? event.message ?? null
}

function inputTransformFromUpdatedInput(
  updatedInput: Record<string, unknown> | undefined,
): PiHookResult | null {
  if (!updatedInput) {
    return null
  }
  const text = updatedInput.text ?? updatedInput.prompt
  if (typeof text !== "string") {
    return null
  }
  const result: PiHookResult = { action: "transform", text }
  if (Array.isArray(updatedInput.images)) {
    result.images = updatedInput.images
  }
  return result
}

function beforeAgentStartResult(
  event: PiEventLike,
  result: PiEnforcerResult | null,
): PiHookResult | void {
  if (!result?.context) {
    advisory(result)
    return
  }
  const systemPrompt = event.systemPrompt || ""
  return {
    systemPrompt: `${systemPrompt}\n\n${result.context}`.trim(),
  }
}

function advisory(result: PiEnforcerResult | null): void {
  if (!result) {
    return
  }
  const message = result.context || result.reason
  if (message) {
    console.warn(`[slopgate] ${message}`)
  }
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
    tool_name: event.toolName || "",
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
  pi.on("tool_call", async (event: PiEventLike, ctx: PiContextLike) => {
    const result = await enforce("tool_call", event, ctx)
    applyUpdatedInput(event, result?.updated_input)
    if (result?.block) {
      return { block: true, reason: result.reason || "Blocked by slopgate" }
    }
    advisory(result)
  })

  pi.on("tool_result", async (event: PiEventLike, ctx: PiContextLike) => {
    const result = await enforce("tool_result", event, ctx)
    advisory(result)
  })

  pi.on("tool_execution_end", async (event: PiEventLike, ctx: PiContextLike) => {
    const result = await enforce("tool_execution_end", event, ctx)
    advisory(result)
  })

  pi.on("input", async (event: PiEventLike, ctx: PiContextLike) => {
    const result = await enforce("input", event, ctx)
    if (result?.block) {
      if (result.reason && ctx.ui?.notify) {
        ctx.ui.notify(result.reason, "warn")
      }
      return { action: "handled" }
    }
    const transform = inputTransformFromUpdatedInput(result?.updated_input)
    if (transform) {
      return transform
    }
    advisory(result)
  })

  pi.on("before_agent_start", async (event: PiEventLike, ctx: PiContextLike) => {
    return beforeAgentStartResult(event, await enforce("before_agent_start", event, ctx))
  })

  pi.on("turn_end", async (event: PiEventLike, ctx: PiContextLike) => {
    advisory(await enforce("turn_end", event, ctx))
  })

  pi.on("agent_end", async (event: PiEventLike, ctx: PiContextLike) => {
    advisory(await enforce("agent_end", event, ctx))
  })
}
