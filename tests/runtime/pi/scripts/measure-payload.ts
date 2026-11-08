/**
 * Measures the enforcer wire bytes for one large Pi tool result.
 *
 * Usage: bun run scripts/measure-payload.ts
 *
 * Loads the staged extension through the pinned native runner with a recording
 * fake enforcer, emits a large tool_result, and prints the serialized payload
 * size so the step-4 payload reduction is a measured number, not a claim.
 */
import { mkdtemp, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { fileURLToPath } from "node:url";
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
  ToolResultEvent,
} from "@earendil-works/pi-coding-agent";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const WORKSPACE_ROOT = path.resolve(SCRIPT_DIR, "../../../..");
const STAGED_PATH = path.join(WORKSPACE_ROOT, "tests/runtime/pi/staged/pi_extension.ts");
const FAKE_ENFORCER = path.join(WORKSPACE_ROOT, "tests/runtime/pi/fake-enforcer/slopgate");

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
    getThinkingLevel: () => "off",
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

function largeResultEvent(): ToolResultEvent {
  const text = "0123456789abcdef".repeat(512);
  return {
    type: "tool_result",
    toolCallId: "measure-large-call",
    toolName: "custom_tool",
    input: { path: "large.txt", pattern: "literal" },
    content: [{ type: "text", text }],
    details: {
      exitCode: 0,
      truncated: false,
      unrelated: { nested: Array.from({ length: 32 }, (_, index) => `detail-${index}`) },
    },
    isError: false,
  };
}

const root = await mkdtemp(path.join(tmpdir(), "slopgate-pi-payload-"));
try {
  const project = path.join(root, "project");
  const recordPath = path.join(root, "payload.jsonl");
  await mkdir(project, { recursive: true });
  await writeFile(path.join(project, "slopgate.toml"), "[slopgate]\nenabled = true\n", "utf8");
  await writeFile(recordPath, "", "utf8");

  process.env.SLOPGATE_BIN = FAKE_ENFORCER;
  process.env.SLOPGATE_PI_RECORD_PATH = recordPath;
  process.env.SLOPGATE_PI_FAKE_MODE = "response";
  process.env.SLOPGATE_PI_FAKE_RESPONSE = "{}";

  const modelRuntime = await ModelRuntime.create({ allowModelNetwork: false, refreshOnCreate: false });
  const registry = new ModelRegistry(modelRuntime);
  const loaded = await discoverAndLoadExtensions(
    [STAGED_PATH],
    project,
    path.join(project, ".pi", "agent"),
    createEventBus(),
  );
  if (loaded.errors.length > 0 || loaded.extensions.length !== 1) {
    throw new Error(`Pi extension load failed: ${JSON.stringify(loaded.errors)}`);
  }
  const sessionManager = SessionManager.inMemory(project, { id: "payload-measure-session" });
  const runner = new ExtensionRunner(loaded.extensions, loaded.runtime, project, sessionManager, registry);
  runner.bindCore(fakeActions(), fakeContextActions());

  const event = largeResultEvent();
  await runner.emitToolResult(event);

  const record = await readFile(recordPath, "utf8");
  const recordLine = record.split(/\r?\n/).find(Boolean) || "";
  const bytes = new TextEncoder().encode(recordLine).byteLength;
  const payload = JSON.parse(recordLine) as Record<string, unknown>;
  const firstContentPart = event.content[0];
  if (firstContentPart?.type !== "text") throw new Error("Large result did not contain text content");
  process.stdout.write(`${JSON.stringify({
    bytes,
    eventChars: firstContentPart.text.length,
    keys: Object.keys(payload).sort(),
  })}\n`);
} finally {
  delete process.env.SLOPGATE_BIN;
  delete process.env.SLOPGATE_PI_RECORD_PATH;
  delete process.env.SLOPGATE_PI_FAKE_MODE;
  delete process.env.SLOPGATE_PI_FAKE_RESPONSE;
  await rm(root, { recursive: true, force: true });
}
