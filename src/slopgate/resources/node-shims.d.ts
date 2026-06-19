/**
 * Ambient type shims for Node.js built-in modules used by resource templates.
 *
 * These templates are installed into their respective platform directories
 * (~/.pi/agent/extensions/pi-slopgate/, ~/.opencode/extensions/)
 * where @types/node is available via their own package.json.
 *
 * At development time in the slopgate source tree, the modules are
 * unavailable, so we declare only the exports actually consumed.
 */

/// <reference lib="es2022" />
declare module "node:child_process" {
  export function spawn(
    command: string,
    args?: readonly string[],
    options?: {
      cwd?: string
      env?: Record<string, string | undefined>
      stdio?: Array<"pipe" | "inherit" | "ignore">
    },
  ): {
    stdin: { write(data: string): void; end(): void }
    stdout: { on(event: "data", handler: (chunk: string | Uint8Array) => void): void }
    stderr: { on(event: "data", handler: (chunk: string | Uint8Array) => void): void }
    on(event: "close", handler: (code: number | null) => void): void
    on(event: "error", handler: (error: Error) => void): void
  }
}

declare module "node:fs" {
  export function existsSync(path: string): boolean
}

declare module "node:path" {
  export function dirname(path: string): string
  export function join(...paths: string[]): string
}

declare module "node:process" {
  interface Process {
    cwd(): string
    env: Record<string, string | undefined>
  }
  const process: Process
  export default process
}
