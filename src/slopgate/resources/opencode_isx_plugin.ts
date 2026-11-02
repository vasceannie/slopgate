import { existsSync } from "node:fs"
import { Plugin } from "@opencode/plugin"

declare const Bun: {
  env: Record<string, string | undefined>
  spawn(
    command: string[],
    options: {
      cwd?: string
      stdin: "ignore"
      stdout: "pipe"
      stderr: "pipe"
      env: Record<string, string | undefined>
      signal?: AbortSignal
    },
  ): {
    stdout: ReadableStream<Uint8Array>
    stderr: ReadableStream<Uint8Array>
    exited: Promise<number>
  }
}

const ISX_CONFIG = `${Bun.env.HOME}/.config/isx/config.json`

type IndexInfo = {
  name: string
  repository?: {
    clone_url?: string
    ssh_url?: string
    full_name?: string
    name?: string
  }
}

type ModelsInput = {
  all?: boolean
}

type UseModelInput = {
  model: string
  force?: boolean
}

type AddRepoInput = {
  repo?: string
}

type SearchInput = {
  query: string
}

type TargetInput = {
  target?: string
}

const rejectOnAbort = (signal: AbortSignal): Promise<never> =>
  new Promise((_resolve, reject) => {
    signal.addEventListener("abort", () => reject(signal.reason), { once: true })
  })

const runCommand = async (command: string[], signal: AbortSignal, cwd?: string): Promise<string> => {
  signal.throwIfAborted()
  const proc = Bun.spawn(command, {
    cwd,
    stdin: "ignore",
    stdout: "pipe",
    stderr: "pipe",
    env: Bun.env,
    signal,
  })

  // A descendant can keep the pipes open after the kill, so abort must not wait on them.
  const [stdout, stderr, exitCode] = await Promise.race([
    Promise.all([new Response(proc.stdout).text(), new Response(proc.stderr).text(), proc.exited]),
    rejectOnAbort(signal),
  ])
  const combined = [stdout.trim(), stderr.trim()].filter(Boolean).join("\n")

  if (exitCode !== 0) {
    throw new Error(combined || `${command[0]} exited with code ${exitCode}`)
  }

  return combined || "ok"
}

const runIsx = async (args: string[], signal: AbortSignal): Promise<string> => {
  if (!existsSync(ISX_CONFIG)) {
    throw new Error("isx is not initialized yet. Run `isx init --provider litellm --integration opencode-tool` first.")
  }
  return runCommand(["isx", ...args], signal)
}

const maybeCurrentRepoRemote = async (cwd: string, signal: AbortSignal): Promise<string | null> => {
  try {
    const value = await runCommand(["git", "config", "--get", "remote.origin.url"], signal, cwd)
    return value.trim() || null
  } catch {
    return null
  }
}

const repoTokens = (value?: string | null): string[] => {
  const raw = value?.trim()
  if (!raw) return []

  const tokens = new Set<string>()
  const add = (item?: string | null) => {
    const text = item?.trim()
    if (!text) return
    tokens.add(text)
    tokens.add(text.replace(/\.git$/, ""))
  }

  add(raw)

  const sshMatch = raw.match(/^git@[^:]+:(.+?)(?:\.git)?$/)
  if (sshMatch) add(sshMatch[1])

  const httpsMatch = raw.match(/^[a-z]+:\/\/[^/]+\/(.+?)(?:\.git)?$/i)
  if (httpsMatch) add(httpsMatch[1])

  return [...tokens]
}

const listIndexes = async (signal: AbortSignal): Promise<IndexInfo[]> => {
  const raw = await runIsx(["list", "--json"], signal)
  return JSON.parse(raw) as IndexInfo[]
}

const findIndexForRepo = async (repo: string, signal: AbortSignal): Promise<IndexInfo | null> => {
  const wanted = new Set(repoTokens(repo))
  const indexes = await listIndexes(signal)

  for (const item of indexes) {
    const repoInfo = item.repository ?? {}
    const candidates = [
      item.name,
      repoInfo.clone_url,
      repoInfo.ssh_url,
      repoInfo.full_name,
      repoInfo.name,
    ]
    for (const candidate of candidates) {
      for (const token of repoTokens(candidate)) {
        if (wanted.has(token)) {
          return item
        }
      }
    }
  }

  return null
}

const requireRepoRemote = async (cwd: string, signal: AbortSignal): Promise<string> => {
  const remote = await maybeCurrentRepoRemote(cwd, signal)
  if (!remote) {
    throw new Error("This action needs a git repo with an origin remote, or an explicit repo/target argument.")
  }
  return remote
}

const requireIndexedCurrentRepo = async (
  cwd: string,
  action: string,
  signal: AbortSignal,
): Promise<{ remote: string; index: IndexInfo }> => {
  const remote = await requireRepoRemote(cwd, signal)
  const index = await findIndexForRepo(remote, signal)
  if (!index) {
    throw new Error(`Current repo is not indexed in isx yet (${remote}). Run isx_add_repo with this repo before trying to ${action}.`)
  }
  return { remote, index }
}

const withTitle = async (
  context: { progress: (update: { title: string }) => Promise<void> },
  title: string,
  fn: () => Promise<string>,
): Promise<{ content: string }> => {
  await context.progress({ title })
  return { content: await fn() }
}

const resolveRepoArg = async (repo: string | undefined, cwd: string, signal: AbortSignal): Promise<string> =>
  repo || await requireRepoRemote(cwd, signal)

const resolveIndexedTarget = async (
  target: string | undefined,
  cwd: string,
  action: string,
  signal: AbortSignal,
): Promise<string> => {
  if (target) return target
  const resolved = await requireIndexedCurrentRepo(cwd, action, signal)
  return resolved.index.name || resolved.remote
}

const resolveSearchGuard = async (cwd: string, signal: AbortSignal): Promise<void> => {
  const remote = await maybeCurrentRepoRemote(cwd, signal)
  if (!remote) return
  const index = await findIndexForRepo(remote, signal)
  if (!index) {
    throw new Error(`Current repo is not indexed in isx yet (${remote}). Run isx_add_repo first so semantic search does not silently hit some other repo.`)
  }
}

export default Plugin.define({
  id: "slopgate.isx",
  async setup(ctx) {
    const resolveSessionDirectory = async (
      sessionID: Parameters<typeof ctx.session.get>[0]["sessionID"],
    ): Promise<string> => {
      const session = await ctx.session.get({ sessionID })
      return session.location.directory
    }

    await ctx.tool.transform((editor) => {
      editor.add({
        name: "isx_doctor",
        description: "Check whether the local isx semantic-search runtime is configured and reachable.",
        input: {
          type: "object",
          properties: {},
          additionalProperties: false,
        },
        execute: async (_input, context) => withTitle(context, "isx doctor", () => runIsx(["doctor"], context.signal)),
      })

      editor.add({
        name: "isx_list_indexes",
        description: "List locally known islands indexes managed through isx.",
        input: {
          type: "object",
          properties: {},
          additionalProperties: false,
        },
        execute: async (_input, context) => withTitle(context, "isx list", () => runIsx(["list"], context.signal)),
      })

      editor.add({
        name: "isx_models",
        description: "List embedding models/routes available to isx.",
        input: {
          type: "object",
          properties: {
            all: {
              type: "boolean",
              description: "Show all models instead of only embedding-ish ones.",
            },
          },
          additionalProperties: false,
        },
        execute: async (input, context) => {
          const { all } = input as ModelsInput
          return withTitle(context, "isx models", () => runIsx(all ? ["models", "--all"] : ["models"], context.signal))
        },
      })

      editor.add({
        name: "isx_use_model",
        description: "Switch isx to a different embedding model.",
        input: {
          type: "object",
          properties: {
            model: {
              type: "string",
              minLength: 1,
              description: "Model or routed model name.",
            },
            force: {
              type: "boolean",
              description: "Skip remote model validation.",
            },
          },
          required: ["model"],
          additionalProperties: false,
        },
        execute: async (input, context) => {
          const { model, force } = input as UseModelInput
          return withTitle(context, `isx use ${model}`, () => runIsx(force ? ["use", model, "--force"] : ["use", model], context.signal))
        },
      })

      editor.add({
        name: "isx_add_repo",
        description: "Clone and index a repository with isx. If repo is omitted, uses the current git origin remote.",
        input: {
          type: "object",
          properties: {
            repo: {
              type: "string",
              minLength: 1,
              description: "Git repository URL. Optional when run inside a git repo with origin set.",
            },
          },
          additionalProperties: false,
        },
        execute: async (input, context) => {
          const { repo } = input as AddRepoInput
          const directory = await resolveSessionDirectory(context.sessionID)
          const resolved = await resolveRepoArg(repo, directory, context.signal)
          return withTitle(context, `isx add ${resolved}`, () => runIsx(["add", resolved], context.signal))
        },
      })

      editor.add({
        name: "isx_search",
        description: "Run semantic search across indexed repositories. Inside a git repo, this first checks that the current repo has actually been indexed.",
        input: {
          type: "object",
          properties: {
            query: {
              type: "string",
              minLength: 1,
              description: "Semantic search query.",
            },
          },
          required: ["query"],
          additionalProperties: false,
        },
        execute: async (input, context) => {
          const { query } = input as SearchInput
          const directory = await resolveSessionDirectory(context.sessionID)
          await resolveSearchGuard(directory, context.signal)
          return withTitle(context, `isx search ${query}`, () => runIsx(["search", query], context.signal))
        },
      })

      editor.add({
        name: "isx_reindex",
        description: "Remove and rebuild an index from its saved clone URL. If target is omitted, uses the current indexed repo.",
        input: {
          type: "object",
          properties: {
            target: {
              type: "string",
              minLength: 1,
              description: "Index name, repo URL, or known repo identifier. Optional when run inside an indexed repo.",
            },
          },
          additionalProperties: false,
        },
        execute: async (input, context) => {
          const { target } = input as TargetInput
          const directory = await resolveSessionDirectory(context.sessionID)
          const resolved = await resolveIndexedTarget(target, directory, "reindex it", context.signal)
          return withTitle(context, `isx reindex ${resolved}`, () => runIsx(["reindex", resolved], context.signal))
        },
      })

      editor.add({
        name: "isx_sync",
        description: "Sync indexed repositories. If target is omitted, syncs the current indexed repo when possible, otherwise all indexes.",
        input: {
          type: "object",
          properties: {
            target: {
              type: "string",
              minLength: 1,
              description: "Optional index name to sync.",
            },
          },
          additionalProperties: false,
        },
        execute: async (input, context) => {
          const { target } = input as TargetInput
          const directory = await resolveSessionDirectory(context.sessionID)
          const remote = await maybeCurrentRepoRemote(directory, context.signal)
          if (target) {
            return withTitle(context, `isx sync ${target}`, () => runIsx(["sync", target], context.signal))
          }
          if (remote) {
            const index = await findIndexForRepo(remote, context.signal)
            if (!index) {
              throw new Error(`Current repo is not indexed in isx yet (${remote}). Run isx_add_repo first before syncing it.`)
            }
            return withTitle(context, `isx sync ${index.name}`, () => runIsx(["sync", index.name], context.signal))
          }
          return withTitle(context, "isx sync", () => runIsx(["sync"], context.signal))
        },
      })

      editor.add({
        name: "isx_remove",
        description: "Remove an isx index. If target is omitted, removes the current indexed repo after confirmation.",
        input: {
          type: "object",
          properties: {
            target: {
              type: "string",
              minLength: 1,
              description: "Index name, repo URL, or known repo identifier.",
            },
          },
          additionalProperties: false,
        },
        execute: async (input, context) => {
          const { target } = input as TargetInput
          const directory = await resolveSessionDirectory(context.sessionID)
          const resolved = await resolveIndexedTarget(target, directory, "remove it", context.signal)
          await ctx.permission.assert({
            sessionID: context.sessionID,
            agent: context.agent,
            action: "edit",
            resources: [resolved],
            source: {
              type: "tool",
              messageID: context.messageID,
              id: context.id,
            },
          })
          // --force only skips the CLI's own prompt; the approval above is the gate.
          return withTitle(context, `isx remove ${resolved}`, () => runIsx(["remove", resolved, "--force"], context.signal))
        },
      })
    })
  },
})
