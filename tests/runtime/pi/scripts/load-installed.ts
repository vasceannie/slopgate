/**
 * Loads an installed Pi Slopgate extension artifact through the pinned native
 * discovery + ExtensionRunner and proves guard/enforcer behavior on the
 * installed bytes.
 *
 * Usage: bun run scripts/load-installed.ts <installed-index.ts> <project-cwd> <agent-dir> <record-path>
 */
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { pathToFileURL } from "node:url";
import * as path from "node:path";

import {
  ExtensionRunner,
  ModelRegistry,
  ModelRuntime,
  SessionManager,
  createEventBus,
  discoverAndLoadExtensions,
} from "@earendil-works/pi-coding-agent";
import type {
  ExtensionActions,
  ExtensionContextActions,
  ExtensionFactory,
} from "@earendil-works/pi-coding-agent";

const FAKE_ENFORCER = path.resolve(import.meta.dir, "../../omp/fake-enforcer/slopgate");

const [indexPath, projectCwd, agentDir, recordPath] = process.argv.slice(2);
if (
  !indexPath || !path.isAbsolute(indexPath) ||
  !projectCwd || !path.isAbsolute(projectCwd) ||
  !agentDir || !path.isAbsolute(agentDir) ||
  !recordPath
) {
  process.stderr.write(
    "Usage: bun run scripts/load-installed.ts <absolute-index.ts> <absolute-project> <absolute-agent-dir> <absolute-record-path>\n",
  );
  process.exit(2);
}

// The installed module reads these at import time.
process.env.SLOPGATE_BIN = FAKE_ENFORCER;
process.env.SLOPGATE_FAKE_RECORD_PATH = recordPath;

type RecordedPayload = {
  readonly hook_event_name?: unknown
  readonly session_id?: unknown
  readonly tool_name?: unknown
}

async function readRecordedPayload(): Promise<RecordedPayload> {
  const parsed: unknown = JSON.parse(await Bun.file(recordPath).text());
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error(`Recorded payload is not an object: ${recordPath}`);
  }
  return parsed as RecordedPayload;
}

function fakeActions(): ExtensionActions {
  return {
    sendMessage: () => {},
    sendUserMessage: () => {},
    appendEntry: () => {},
    setSessionName: async () => {},
    setLabel: () => {},
    getActiveTools: () => [],
    getAllTools: () => [],
    setActiveTools: async () => {},
    refreshTools: async () => {},
    getCommands: () => [],
    getSessionName: () => undefined,
    setModel: async () => false,
    getThinkingLevel: () => undefined,
    setThinkingLevel: () => {},
  };
}

function fakeContextActions(): ExtensionContextActions {
  return {
    getModel: () => undefined,
    isIdle: () => true,
    abort: () => {},
    hasPendingMessages: () => false,
    shutdown: () => {},
    getContextUsage: () => undefined,
    compact: async () => {},
    getSystemPrompt: () => "",
  };
}

function fakeActions(): ExtensionActions {
  return {
    sendMessage: () => {},
    sendUserMessage: () => {},
    appendEntry: () => {},
    setSessionName: async () => {},
    setLabel: () => {},
    getActiveTools: () => [],
    getAllTools: () => [],
    setActiveTools: async () => {},
    refreshTools: async () => {},
    getCommands: () => [],
  };
}

function fakeContextActions(): ExtensionContextActions {
  return {
    getModel: () => undefined,
    isIdle: () => true,
    abort: () => {},
    hasPendingMessages: () => false,
    shutdown: () => {},
    getContextUsage: () => undefined,
    compact: async () => {},
    getSystemPrompt: () => [],
  };
}

const scratch = await mkdtemp(path.join(tmpdir(), "slopgate-pi-installed-"));
try {
  const modelRuntime = await ModelRuntime.create({ allowModelNetwork: false, refreshOnCreate: false });
  const registry = new ModelRegistry(modelRuntime);
  const loaded = await discoverAndLoadExtensions([indexPath], projectCwd, agentDir, createEventBus());
  if (loaded.errors.length > 0 || loaded.extensions.length === 0) {
    throw new Error(`Installed Pi extension load failed: ${JSON.stringify(loaded.errors)}`);
  }
  // Both scopes are installed in this proof; native discovery must surface the
  // project artifact (project precedence) alongside the user artifact.
  const projectExtension = loaded.extensions.find(extension => extension.path === indexPath);
  if (!projectExtension) {
    throw new Error(`Installed Pi discovery missed the project artifact: ${JSON.stringify(loaded.extensions)}`);
  }
  const sessionManager = SessionManager.inMemory(projectCwd);
  const runner = new ExtensionRunner(loaded.extensions, loaded.runtime, projectCwd, sessionManager, registry);
  runner.bindCore(fakeActions(), fakeContextActions());

  const writeResult = await runner.emitToolCall({
    type: "tool_call",
    toolCallId: "installed-write",
    toolName: "write",
    input: { path: "slopgate.toml", content: "blocked" },
  });
  if (!writeResult?.block || typeof writeResult.reason !== "string" || !writeResult.reason.includes("slopgate.toml")) {
    throw new Error(`Installed artifact did not block the protected write: ${JSON.stringify(writeResult)}`);
  }

  const readResult = await runner.emitToolCall({
    type: "tool_call",
    toolCallId: "installed-read",
    toolName: "read",
    input: { path: "README.md" },
  });
  if (readResult?.block) {
    throw new Error(`Installed artifact blocked an allowed read: ${JSON.stringify(readResult)}`);
  }
  const payload = await readRecordedPayload();
  if (payload.hook_event_name !== "tool_call" || payload.tool_name !== "read") {
    throw new Error(`Installed artifact recorded an unexpected payload: ${JSON.stringify(payload)}`);
  }
  if (payload.session_id !== sessionManager.getSessionId()) {
    throw new Error("Installed artifact did not forward the native session identity");
  }

  process.stdout.write(`${JSON.stringify({
    blockedWrite: writeResult.reason,
    extensions: loaded.extensions.length,
    loaded: true,
    session: payload.session_id,
  })}\n`);
} finally {
  delete process.env.SLOPGATE_BIN;
  delete process.env.SLOPGATE_FAKE_RECORD_PATH;
  await rm(scratch, { force: true, recursive: true });
}
