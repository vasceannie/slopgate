/**
 * Loads an installed Pi Slopgate extension artifact through the pinned native
 * discovery + ExtensionRunner and proves guard/enforcer behavior on the
 * installed bytes.
 *
 * Usage: bun run scripts/load-installed.ts <installed-index.ts> <project-cwd> <agent-dir> <record-path>
 */
import { mkdir, readFile, writeFile } from "node:fs/promises";
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
  ToolResultEvent,
} from "@earendil-works/pi-coding-agent";

const FAKE_ENFORCER = path.resolve(import.meta.dir, "../fake-enforcer/slopgate");
const SLOPGATE_CONTEXT_HEADER = "Slopgate hook context for this turn:";
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
process.env.SLOPGATE_PI_RECORD_PATH = recordPath;
process.env.SLOPGATE_PI_FAKE_MODE = "response";
process.env.SLOPGATE_PI_FAKE_RESPONSE = "{}";
await mkdir(path.dirname(recordPath), { recursive: true });
await writeFile(recordPath, "", "utf8");

type RecordedPayload = Record<string, unknown>;

type PackageWrite = { readonly blocked: boolean; readonly reason?: string };

async function checkPackageWrite(
  runner: ExtensionRunner,
  target: string,
  toolCallId: string,
): Promise<PackageWrite> {
  const result = await runner.emitToolCall({
    type: "tool_call",
    toolCallId,
    toolName: "write",
    input: { path: target, content: "blocked" },
  });
  return {
    blocked: result?.block === true,
    ...(typeof result?.reason === "string" ? { reason: result.reason } : {}),
  };
}

function isRecord(value: unknown): value is RecordedPayload {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

async function readRecordedPayloads(): Promise<RecordedPayload[]> {
  const contents = await readFile(recordPath, "utf8");
  return contents.split(/\r?\n/).filter(Boolean).map((line: string) => {
    const value: unknown = JSON.parse(line);
    if (!isRecord(value)) throw new Error("Enforcer recorded a non-object payload");
    return value;
  });
}

function setResponse(response: Record<string, unknown>): void {
  process.env.SLOPGATE_PI_FAKE_MODE = "response";
  process.env.SLOPGATE_PI_FAKE_RESPONSE = JSON.stringify(response);
}

function fakeActions(messages: unknown[]): ExtensionActions {
  return {
    sendMessage: (message) => messages.push(message),
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

function textContent(content: ToolResultEvent["content"] | undefined): string {
  return (content ?? []).flatMap((part) => "text" in part ? [part.text] : []).join("\n");
}

function countOccurrences(text: string, fragment: string): number {
  return text.split(fragment).length - 1;
}

const modelRuntime = await ModelRuntime.create({ allowModelNetwork: false, refreshOnCreate: false });
const registry = new ModelRegistry(modelRuntime);
const loaded = await discoverAndLoadExtensions([indexPath], projectCwd, agentDir, createEventBus());
if (loaded.errors.length > 0 || loaded.extensions.length === 0) {
  throw new Error(`Installed Pi extension load failed: ${JSON.stringify(loaded.errors)}`);
}
// Both scopes are installed in this proof; native discovery must surface the
// project artifact (project precedence) alongside the user artifact.
const projectExtension = loaded.extensions.find((extension) => extension.path === indexPath);
if (!projectExtension) {
  throw new Error(`Installed Pi discovery missed the project artifact: ${JSON.stringify(loaded.extensions)}`);
}
const sessionManager = SessionManager.inMemory(projectCwd);
const runner = new ExtensionRunner(loaded.extensions, loaded.runtime, projectCwd, sessionManager, registry);
const messages: unknown[] = [];
runner.bindCore(fakeActions(messages), fakeContextActions());

const writeResult = await runner.emitToolCall({
  type: "tool_call",
  toolCallId: "installed-write",
  toolName: "write",
  input: { path: "slopgate.toml", content: "blocked" },
});
if (!writeResult?.block || typeof writeResult.reason !== "string" || !writeResult.reason.includes("slopgate.toml")) {
  throw new Error(`Installed artifact did not block the protected write: ${JSON.stringify(writeResult)}`);
}


const packageWrites = {
  index: await checkPackageWrite(
    runner,
    path.join(path.dirname(indexPath), "index.ts"),
    "installed-package-index",
  ),
  manifest: await checkPackageWrite(
    runner,
    path.join(path.dirname(indexPath), "package.json"),
    "installed-package-manifest",
  ),
};
setResponse({});
const readResult = await runner.emitToolCall({
  type: "tool_call",
  toolCallId: "installed-read",
  toolName: "read",
  input: { path: "README.md" },
});
if (readResult?.block) {
  throw new Error(`Installed artifact blocked an allowed read: ${JSON.stringify(readResult)}`);
}
const ordinaryPayload = (await readRecordedPayloads()).find((payload) => payload.tool_call_id === "installed-read");
if (
  ordinaryPayload?.hook_event_name !== "tool_call" ||
  ordinaryPayload.tool_name !== "read" ||
  ordinaryPayload.session_id !== sessionManager.getSessionId()
) {
  throw new Error(`Installed artifact did not evaluate the ordinary call with native identity: ${JSON.stringify(ordinaryPayload)}`);
}

setResponse({ context: "INSTALLED_SESSION_CONTEXT" });
await runner.emit({ type: "session_start", reason: "startup" });
for (const [index, prompt] of ["first installed prompt", "second installed prompt"].entries()) {
  setResponse({ context: "INSTALLED_PROMPT_CONTEXT" });
  await runner.emitInput(prompt, undefined, "interactive");
  const prepared = await runner.emitBeforeAgentStart(prompt, undefined, "unchanged base prompt", { cwd: projectCwd });
  const systemPrompt = prepared?.systemPrompt ?? "";
  if (!systemPrompt.includes("INSTALLED_SESSION_CONTEXT") || !systemPrompt.includes("INSTALLED_PROMPT_CONTEXT")) {
    throw new Error(`Installed artifact omitted context for prompt ${index + 1}: ${systemPrompt}`);
  }
  if (countOccurrences(systemPrompt, SLOPGATE_CONTEXT_HEADER) !== 1) {
    throw new Error(`Installed artifact emitted an unbounded context block for prompt ${index + 1}: ${systemPrompt}`);
  }
  if ((prepared?.messages ?? []).length !== 0) {
    throw new Error(`Installed artifact returned persistent messages for prompt ${index + 1}`);
  }
}
if (messages.length !== 0) {
  throw new Error(`Installed artifact emitted custom chat messages: ${JSON.stringify(messages)}`);
}
const evaluatedPayloads = await readRecordedPayloads();
if (evaluatedPayloads.filter((payload) => payload.hook_event_name === "session_start").length !== 1) {
  throw new Error("Installed artifact reevaluated startup while preparing repeated prompts");
}
if (evaluatedPayloads.filter((payload) => payload.hook_event_name === "input").length !== 2) {
  throw new Error("Installed artifact did not evaluate both prompt inputs");
}

setResponse({ context: "INSTALLED_POST_TOOL_REPAIR_CONTEXT" });
const toolResultEvent: ToolResultEvent = {
  type: "tool_result",
  toolCallId: "installed-repair-result",
  toolName: "custom_tool",
  input: {},
  content: [{ type: "text", text: "installed original tool output" }],
  details: { unrelated: "preserved" },
  isError: false,
};
const toolResultPatch = await runner.emitToolResult(toolResultEvent);
const modelVisibleResult = textContent(toolResultPatch?.content);
if (
  !modelVisibleResult.includes("installed original tool output") ||
  !modelVisibleResult.includes("Slopgate findings:\n") ||
  !modelVisibleResult.includes("INSTALLED_POST_TOOL_REPAIR_CONTEXT")
) {
  throw new Error(`Installed artifact did not return model-visible tool guidance: ${modelVisibleResult}`);
}
const toolResultDetails = isRecord(toolResultPatch?.details) ? toolResultPatch.details : {};
if (toolResultDetails.unrelated !== "preserved" || messages.length !== 0) {
  throw new Error("Installed artifact dropped native result details or emitted a duplicate message");
}
const latestPayloads = await readRecordedPayloads();
const resultPayload = latestPayloads.find(
  (payload) => payload.hook_event_name === "tool_result" && payload.tool_call_id === "installed-repair-result",
);
if (!resultPayload || !("tool_result" in resultPayload) || "tool_response" in resultPayload || "pi_event" in resultPayload) {
  throw new Error(`Installed artifact emitted a non-canonical result payload: ${JSON.stringify(resultPayload)}`);
}

const projectExtensionPath = pathToFileURL(indexPath).href;
process.stdout.write(`${JSON.stringify({
  blockedWrite: writeResult.reason,
  extensions: loaded.extensions.length,
  loaded: true,
  modelVisibleRepair: modelVisibleResult,
  packageWrites,
  projectExtensionPath,
  promptsPrepared: 2,
  session: ordinaryPayload.session_id,
})}\n`);

delete process.env.SLOPGATE_BIN;
delete process.env.SLOPGATE_PI_RECORD_PATH;
delete process.env.SLOPGATE_PI_FAKE_MODE;
delete process.env.SLOPGATE_PI_FAKE_RESPONSE;
