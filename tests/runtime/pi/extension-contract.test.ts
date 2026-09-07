import { afterEach, describe, expect, test } from "bun:test";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import * as path from "node:path";

import {
  ExtensionRunner,
  ModelRegistry,
  ModelRuntime,
  SessionManager,
  createEventBus,
  createExtensionRuntime,
  discoverAndLoadExtensions,
} from "@earendil-works/pi-coding-agent";
import type {
  ExtensionActions,
  ExtensionContextActions,
  ToolCallEvent,
  ToolExecutionEndEvent,
  TurnEndEvent,
} from "@earendil-works/pi-coding-agent";

type PiRuntimeHarness = {
  readonly runner: ExtensionRunner;
  readonly sessionManager: SessionManager;
  readonly modelRuntime: ModelRuntime;
};

const WORKSPACE_ROOT = path.resolve(import.meta.dir, "../../..");
const STAGED_PATH = path.join(import.meta.dir, "staged/pi_extension.ts");
const temporaryRoots: string[] = [];

function fakeActions(): ExtensionActions {
  return {
    sendMessage: () => {},
    sendUserMessage: () => {},
    appendEntry: () => {},
    setSessionName: async () => {},
    getSessionName: () => undefined,
    setLabel: () => {},
    getActiveTools: () => [],
    getAllTools: () => [],
    setActiveTools: async () => {},
    refreshTools: async () => {},
    getCommands: () => [],
    setModel: async () => false,
    getThinkingLevel: () => undefined,
    setThinkingLevel: () => {},
  };
}

function fakeContextActions(): ExtensionContextActions {
  return {
    getModel: () => undefined,
    getScopedModels: () => [],
    isIdle: () => true,
    isProjectTrusted: () => true,
    getSignal: () => undefined,
    abort: () => {},
    hasPendingMessages: () => false,
    shutdown: () => {},
    getContextUsage: () => undefined,
    compact: () => {},
    getSystemPrompt: () => "base prompt",
  };
}

async function createHarness(cwd: string, enforcer: string, recordPath: string): Promise<PiRuntimeHarness> {
  const modelRuntime = await ModelRuntime.create({ allowModelNetwork: false, refreshOnCreate: false });
  const registry = new ModelRegistry(modelRuntime);
  process.env.SLOPGATE_BIN = enforcer;
  process.env.SLOPGATE_FAKE_RECORD_PATH = recordPath;
  const loaded = await discoverAndLoadExtensions(
    [STAGED_PATH],
    cwd,
    path.join(cwd, ".pi", "agent"),
    createEventBus(),
  );
  if (loaded.errors.length > 0 || loaded.extensions.length !== 1) {
    throw new Error(`Pi extension load failed: ${JSON.stringify(loaded.errors)}`);
  }
  const sessionManager = SessionManager.inMemory(cwd, { id: "native-pi-session" });
  const runner = new ExtensionRunner(loaded.extensions, loaded.runtime, cwd, sessionManager, registry);
  runner.bindCore(fakeActions(), fakeContextActions());
  return { runner, sessionManager, modelRuntime };
}

async function readRecord(recordPath: string): Promise<Record<string, unknown>> {
  const parsed: unknown = JSON.parse(await Bun.file(recordPath).text());
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error(`Pi enforcer record is not an object: ${recordPath}`);
  }
  return parsed as Record<string, unknown>;
}

async function withHarness(
  callback: (harness: PiRuntimeHarness, recordPath: string) => Promise<void>,
): Promise<void> {
  const root = await mkdtemp(path.join(tmpdir(), "slopgate-pi-contract-"));
  temporaryRoots.push(root);
  const project = path.join(root, "project");
  const recordPath = path.join(root, "enforcer.json");
  await mkdir(project, { recursive: true });
  await writeFile(path.join(project, "slopgate.toml"), "[slopgate]\nenabled = true\n", "utf8");
  const fakeEnforcer = path.join(WORKSPACE_ROOT, "tests/runtime/omp/fake-enforcer/slopgate");
  const harness = await createHarness(project, fakeEnforcer, recordPath);
  try {
    await callback(harness, recordPath);
  } finally {
    delete process.env.SLOPGATE_BIN;
    delete process.env.SLOPGATE_FAKE_RECORD_PATH;
    delete process.env.SLOPGATE_FAKE_RESPONSE;
  }
}

afterEach(async () => {
  await Promise.all(temporaryRoots.splice(0).map(root => rm(root, { recursive: true, force: true })));
});

describe("native Pi extension contract", () => {
  test("loads through the native runner and forwards native session identity", async () => {
    await withHarness(async ({ runner }, recordPath) => {
      const event: ToolCallEvent = {
        type: "tool_call",
        toolCallId: "native-session-call",
        toolName: "read",
        input: { path: "README.md" },
      };
      await runner.emitToolCall(event);
      const payload = await readRecord(recordPath);
      expect(payload.session_id).toBe("native-pi-session");
    });
  });

  test("applies native tool-call input revisions in place", async () => {
    await withHarness(async ({ runner }, recordPath) => {
      process.env.SLOPGATE_FAKE_RESPONSE = JSON.stringify({ updated_input: { path: "rewritten.md" } });
      const event: ToolCallEvent = {
        type: "tool_call",
        toolCallId: "native-rewrite-call",
        toolName: "read",
        input: { path: "original.md" },
      };

      await runner.emitToolCall(event);

      expect(event.input).toEqual({ path: "rewritten.md" });
      expect((await readRecord(recordPath)).tool_name).toBe("read");
    });
  });

  test("forwards native turn_end.message to the enforcer payload", async () => {
    await withHarness(async ({ runner }, recordPath) => {
      const message = {
        role: "assistant",
        content: [{ type: "text", text: "turn response" }],
        api: "contract",
        provider: "contract",
        model: "contract",
        usage: {
          input: 0,
          output: 0,
          cacheRead: 0,
          cacheWrite: 0,
          totalTokens: 0,
          cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
        },
        stopReason: "stop",
        timestamp: 0,
      } as const;
      const event: TurnEndEvent = { type: "turn_end", turnIndex: 1, message, toolResults: [] };

      await runner.emit(event);

      expect((await readRecord(recordPath)).stop_response).toBe("turn response");
    });
  });

  test("dispatches native tool_execution_end handlers", async () => {
    await withHarness(async ({ runner }, recordPath) => {
      const event: ToolExecutionEndEvent = {
        type: "tool_execution_end",
        toolCallId: "native-execution-end-call",
        toolName: "read",
        result: "done",
        isError: false,
      };

      await runner.emit(event);

      expect((await readRecord(recordPath)).hook_event_name).toBe("tool_execution_end");
    });
  });
});
