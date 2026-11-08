/**
 * Loads an OMP package path obtained from `omp plugin list --json` through the
 * pinned native ExtensionRunner and exercises its installed bytes.
 *
 * Usage: bun run scripts/load-installed.ts <registered-index.ts> <project-cwd> <record-path>
 */
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { pathToFileURL } from "node:url";
import * as path from "node:path";

import { ModelRegistry } from "@oh-my-pi/pi-coding-agent/config/model-registry";
import { ExtensionRuntime, loadExtensionFromFactory } from "@oh-my-pi/pi-coding-agent/extensibility/extensions/loader";
import { ExtensionRunner } from "@oh-my-pi/pi-coding-agent/extensibility/extensions/runner";
import type {
  ExtensionActions,
  ExtensionContextActions,
  ExtensionFactory,
} from "@oh-my-pi/pi-coding-agent/extensibility/extensions/types";
import { AuthStorage } from "@oh-my-pi/pi-coding-agent/session/auth-storage";
import { SessionManager } from "@oh-my-pi/pi-coding-agent/session/session-manager";
import { EventBus } from "@oh-my-pi/pi-coding-agent/utils/event-bus";

const FAKE_ENFORCER = path.resolve(import.meta.dir, "../fake-enforcer/slopgate");
const [indexPath, projectCwd, recordPath] = process.argv.slice(2);
if (!indexPath || !path.isAbsolute(indexPath) || !projectCwd || !path.isAbsolute(projectCwd) || !recordPath) {
  process.stderr.write("Usage: bun run scripts/load-installed.ts <registered-index.ts> <absolute-cwd> <absolute-record-path>\n");
  process.exit(2);
}

process.env.SLOPGATE_BIN = FAKE_ENFORCER;
process.env.SLOPGATE_FAKE_RECORD_PATH = recordPath;
const invocationLogPath = `${recordPath}.log`;
process.env.SLOPGATE_FAKE_LOG_PATH = invocationLogPath;

const PROMPT_HEADER = "Slopgate hook context for this turn:";
const FINDINGS_HEADER = "Slopgate findings:\n";

type RecordedPayload = {
  readonly hook_event_name?: unknown;
  readonly omp_event?: unknown;
  readonly tool_call_id?: unknown;
  readonly tool_response?: unknown;
  readonly session_id?: unknown;
  readonly tool_name?: unknown;
};

type ToolResult = { readonly block?: boolean; readonly reason?: string } | undefined;
type PackageWrite = { readonly blocked: boolean; readonly reason?: string };

function setResponse(response: Record<string, unknown>): void {
  process.env.SLOPGATE_FAKE_RESPONSE = JSON.stringify(response);
}

async function readInvocationLog(): Promise<readonly string[]> {
  if (!(await Bun.file(invocationLogPath).exists())) return [];
  return (await Bun.file(invocationLogPath).text()).split("\n").filter((line) => line.length > 0);
}

function textOf(content: readonly { readonly type: string; readonly text?: string }[] | undefined): string {
  return (content ?? []).flatMap((part) => (typeof part.text === "string" ? [part.text] : [])).join("\n");
}

function countOccurrences(text: string, fragment: string): number {
  return text.split(fragment).length - 1;
}

async function readRecordedPayload(): Promise<RecordedPayload> {
  const parsed: unknown = JSON.parse(await Bun.file(recordPath).text());
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error(`Recorded payload is not an object: ${recordPath}`);
  }
  return parsed as RecordedPayload;
}

function requireBlock(result: ToolResult, label: string): string {
  if (!result?.block || typeof result.reason !== "string" || !result.reason.includes("slopgate.toml")) {
    throw new Error(`Installed artifact did not block the protected target (${label}): ${JSON.stringify(result)}`);
  }
  return result.reason;
}

async function checkPackageWrite(runner: ExtensionRunner, target: string): Promise<PackageWrite> {
  const result = await runner.emitToolCall({
    type: "tool_call",
    toolCallId: `package-write-${path.basename(target)}`,
    toolName: "write",
    input: { path: target, content: "blocked" },
  });
  return {
    blocked: result?.block === true,
    ...(typeof result?.reason === "string" ? { reason: result.reason } : {}),
  };
}

const scratch = await mkdtemp(path.join(tmpdir(), "slopgate-omp-installed-"));
try {
  const authStorage = await AuthStorage.create(path.join(scratch, "auth.db"));
  const modelRegistry = new ModelRegistry(authStorage, path.join(scratch, "models.yml"), {
    cacheDbPath: path.join(scratch, "models-cache.db"),
    ignoreLocalModelConfig: true,
  });
  const sessionManager = SessionManager.inMemory(projectCwd);
  const runtime = new ExtensionRuntime();
  // Runtime module loading is required because indexPath comes from the native inventory.
  const installedModule: { default: ExtensionFactory } = await import(pathToFileURL(indexPath).href);
  const extension = await loadExtensionFromFactory(installedModule.default, projectCwd, new EventBus(), runtime, "slopgate-installed");
  const runner = new ExtensionRunner([extension], runtime, projectCwd, sessionManager, modelRegistry);
  let customMessages = 0;
  const actions = {
    sendMessage: () => {
      customMessages += 1;
    },
    sendUserMessage: () => {},
    appendEntry: () => {},
    setLabel: () => {},
    getActiveTools: () => [],
    getAllTools: () => [],
    setActiveTools: async () => {},
    getCommands: () => [],
    setModel: async () => false,
    getThinkingLevel: () => undefined,
    setThinkingLevel: () => {},
    getServiceTiers: () => ({}),
    setServiceTier: () => {},
    getSessionName: () => undefined,
    setSessionName: async () => {},
  } satisfies ExtensionActions;
  const contextActions = {
    getModel: () => undefined,
    isIdle: () => true,
    abort: () => {},
    hasPendingMessages: () => false,
    shutdown: () => {},
    getContextUsage: () => undefined,
    compact: async () => {},
    getSystemPrompt: () => [],
  } satisfies ExtensionContextActions;
  runner.initialize(actions, contextActions);

  const writeReason = requireBlock(await runner.emitToolCall({
    type: "tool_call",
    toolCallId: "installed-write",
    toolName: "write",
    input: { path: "slopgate.toml", content: "blocked" },
  }), "write");
  const hashlineReason = requireBlock(await runner.emitToolCall({
    type: "tool_call",
    toolCallId: "installed-hashline",
    toolName: "edit",
    input: { input: "[slopgate.toml#a1b2]\n+enabled = false" },
  }), "hashline");
  const patchReason = requireBlock(await runner.emitToolCall({
    type: "tool_call",
    toolCallId: "installed-apply-patch",
    toolName: "edit",
    input: { input: "*** Begin Patch\n*** Update File: slopgate.toml\n@@\n-enabled = true\n+enabled = false\n*** End Patch" },
  }), "apply-patch");
  const packageWrites = {
    index: await checkPackageWrite(runner, path.join(path.dirname(indexPath), "index.ts")),
    manifest: await checkPackageWrite(runner, path.join(path.dirname(indexPath), "package.json")),
  };
  const readResult = await runner.emitToolCall({
    type: "tool_call",
    toolCallId: "installed-read",
    toolName: "read",
    input: { path: "README.md" },
  });
  if (readResult?.block) throw new Error(`Installed artifact blocked an allowed read: ${JSON.stringify(readResult)}`);
  const payload = await readRecordedPayload();
  if (payload.hook_event_name !== "tool_call" || payload.tool_name !== "read") {
    throw new Error(`Installed artifact recorded an unexpected payload: ${JSON.stringify(payload)}`);
  }
  if (payload.session_id !== sessionManager.getSessionId()) {
    throw new Error("Installed artifact did not forward the native session identity");
  }

  setResponse({ context: "INSTALLED_SESSION_CONTEXT" });
  await runner.emit({ type: "session_start" });
  for (const [index, prompt] of ["first installed prompt", "second installed prompt"].entries()) {
    setResponse({ context: "INSTALLED_PROMPT_CONTEXT" });
    await runner.emitInput(prompt, undefined, "interactive");
    const prepared = await runner.emitBeforeAgentStart(prompt, undefined, ["unchanged base prompt"]);
    const systemPrompt = (prepared?.systemPrompt ?? []).join("\n");
    if (!systemPrompt.includes("INSTALLED_SESSION_CONTEXT") || !systemPrompt.includes("INSTALLED_PROMPT_CONTEXT")) {
      throw new Error(`Installed artifact omitted context for prompt ${index + 1}: ${systemPrompt}`);
    }
    if (countOccurrences(systemPrompt, PROMPT_HEADER) !== 1) {
      throw new Error(`Installed artifact emitted an unbounded context block for prompt ${index + 1}: ${systemPrompt}`);
    }
  }
  if (customMessages !== 0) throw new Error(`Installed artifact emitted ${customMessages} custom chat messages`);
  const evaluated = await readInvocationLog();
  if (evaluated.filter((name) => name === "session_start").length !== 1) {
    throw new Error("Installed artifact reevaluated startup while preparing repeated prompts");
  }
  if (evaluated.filter((name) => name === "input").length !== 2) {
    throw new Error("Installed artifact did not evaluate both prompt inputs");
  }

  setResponse({ context: "INSTALLED_POST_TOOL_REPAIR_CONTEXT" });
  const repaired = await runner.emitToolResult({
    type: "tool_result",
    toolCallId: "installed-repair-result",
    toolName: "custom_tool",
    input: {},
    content: [{ type: "text", text: "installed original tool output" }],
    details: { unrelated: "preserved" },
    isError: false,
  });
  const repairText = textOf(repaired?.content);
  if (
    !repairText.includes("installed original tool output") ||
    !repairText.includes(FINDINGS_HEADER) ||
    !repairText.includes("INSTALLED_POST_TOOL_REPAIR_CONTEXT")
  ) {
    throw new Error(`Installed artifact did not return model-visible tool guidance: ${repairText}`);
  }
  const repairDetails = typeof repaired?.details === "object" && repaired.details !== null ? repaired.details : {};
  if (!("unrelated" in repairDetails) || customMessages !== 0) {
    throw new Error("Installed artifact dropped native result details or emitted a custom message");
  }
  const resultPayload = await readRecordedPayload();
  if (
    resultPayload.hook_event_name !== "tool_result" ||
    resultPayload.tool_call_id !== "installed-repair-result" ||
    "tool_response" in resultPayload ||
    "omp_event" in resultPayload
  ) {
    throw new Error(`Installed artifact emitted a non-canonical result payload: ${JSON.stringify(resultPayload)}`);
  }

  process.stdout.write(`${JSON.stringify({
    modelVisibleRepair: repairText,
    promptsPrepared: 2,
    blocked: { applyPatch: patchReason, hashline: hashlineReason, write: writeReason },
    extensions: 1,
    loaded: true,
    packageWrites,
    session: payload.session_id,
  })}\n`);
  await sessionManager.close();
  authStorage.close();
} finally {
  await rm(scratch, { force: true, recursive: true });
}
