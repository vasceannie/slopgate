import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, test } from "bun:test";
import { watch as watchDirectory } from "node:fs";
import { mkdir, mkdtemp, readFile, rm, symlink, writeFile } from "node:fs/promises";
import { homedir, tmpdir } from "node:os";
import * as path from "node:path";
import { pathToFileURL } from "node:url";

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
  ToolExecutionEndEvent,
  ToolResultEvent,
  TurnEndEvent,
  UserBashEvent,
} from "@earendil-works/pi-coding-agent";

const WORKSPACE_ROOT = path.resolve(import.meta.dir, "../../..");
const STAGED_PATH = path.join(import.meta.dir, "staged/pi_extension.ts");
const FAKE_ENFORCER = path.join(import.meta.dir, "fake-enforcer/slopgate");
const REAL_SLOPGATE = path.join(WORKSPACE_ROOT, ".venv/bin/slopgate");
const ENVIRONMENT_KEYS = [
  "HOME",
  "USERPROFILE",
  "XDG_CONFIG_HOME",
  "XDG_DATA_HOME",
  "XDG_STATE_HOME",
  "XDG_CACHE_HOME",
  "SLOPGATE_BIN",
  "SLOPGATE_SESSION_ID",
  "SLOPGATE_ENFORCER_TIMEOUT_MS",
  "SLOPGATE_DAEMON_SOCKET",
  "SLOPGATE_CONFIG_DIR",
  "SLOPGATE_ROOT",
  "SLOPGATE_PI_RECORD_PATH",
  "SLOPGATE_PI_FAKE_MODE",
  "SLOPGATE_PI_FAKE_RESPONSE",
  "SLOPGATE_PI_FAKE_EXIT_CODE",
  "SLOPGATE_PI_FAKE_REAL_BIN",
  "SLOPGATE_PI_CHILD_PID_PATH",
] as const;

type PiRuntimeHarness = {
  readonly runner: ExtensionRunner;
  readonly sessionManager: SessionManager;
  readonly messages: unknown[];
  readonly cwd: string;
  readonly recordPath: string;
};

const temporaryRoots: string[] = [];
type PiGuardScope = "managed" | "unmanaged";
type PiPackageFile = "index.ts" | "package.json";
type PiPackageAlias =
  | "canonical"
  | "relative"
  | "tilde"
  | "at"
  | "file-url"
  | "symlink-parent"
  | "symlink-leaf"
  | "missing-descendant"
  | "drive-alias"
  | "mnt-drive-alias"
  | "cygdrive-alias";

const PI_GUARD_SCOPES = ["managed", "unmanaged"] as const;
const PI_PACKAGE_FILES = ["index.ts", "package.json"] as const;
const PI_PACKAGE_ALIASES: readonly PiPackageAlias[] = [
  "canonical",
  "relative",
  "tilde",
  "at",
  "file-url",
  "symlink-parent",
  "symlink-leaf",
  "missing-descendant",
  ...(process.platform === "win32"
    ? ["drive-alias", "mnt-drive-alias", "cygdrive-alias"] as const
    : []),
];
const PI_PACKAGE_GUARD_CASES = PI_GUARD_SCOPES.flatMap((scope) =>
  PI_PACKAGE_ALIASES.flatMap((alias) =>
    PI_PACKAGE_FILES.map((file) => [scope, alias, file] as const),
  ),
);

type PiGuardFixture = {
  readonly managedHarness: PiRuntimeHarness;
  readonly unmanagedHarness: PiRuntimeHarness;
  readonly packageDir: string;
  readonly root: string;
  readonly symlinkParent: string;
  readonly siblingDir: string;
  readonly symlinkLeaves: ReadonlyMap<PiPackageFile, string>;
};

const PI_PASS_THROUGH_TARGETS = [
  ["ordinary", "write"],
  ["sibling-prefix", "write"],
  ["literal-at", "write"],
  ["internal-url", "write"],
  ["malformed-file-url", "write"],
  ["package-read", "read"],
] as const;
const PI_PASS_THROUGH_CASES = PI_GUARD_SCOPES.flatMap((scope) =>
  PI_PASS_THROUGH_TARGETS.map(([name, toolName]) => [scope, name, toolName] as const),
);


function guardHarness(scope: PiGuardScope, fixture: PiGuardFixture): PiRuntimeHarness {
  return scope === "managed" ? fixture.managedHarness : fixture.unmanagedHarness;
}

function guardCwd(scope: PiGuardScope, fixture: PiGuardFixture): string {
  return guardHarness(scope, fixture).cwd;
}

function windowsPiDriveAlias(target: string, style: "drive" | "mnt" | "cygdrive"): string {
  const match = /^([A-Za-z]):[\\/](.*)$/.exec(target);
  if (match === null) throw new Error(`Expected a Windows drive path: ${target}`);
  const drive = (match[1] ?? "").toLowerCase();
  const suffix = (match[2] ?? "").replace(/\\/g, "/");
  const prefix = style === "drive" ? "" : `${style}/`;
  return `/${prefix}${drive}/${suffix}`;
}

function packageTargetForAlias(
  alias: PiPackageAlias,
  file: PiPackageFile,
  cwd: string,
  fixture: PiGuardFixture,
): string {
  const canonical = path.join(fixture.packageDir, file);
  switch (alias) {
    case "canonical":
      return canonical;
    case "relative":
      return path.relative(cwd, canonical);
    case "tilde":
      return `~/${path.relative(homedir(), canonical).split(path.sep).join("/")}`;
    case "at":
      return `@${canonical}`;
    case "file-url":
      return pathToFileURL(canonical).href;
    case "symlink-parent":
      return path.join(fixture.symlinkParent, file);
    case "symlink-leaf": {
      const target = fixture.symlinkLeaves.get(file);
      if (target === undefined) throw new Error(`Missing ${file} symlink fixture`);
      return target;
    }
    case "missing-descendant":
      return path.join(fixture.packageDir, "nested", `${file}.missing`);
    case "drive-alias":
      return windowsPiDriveAlias(canonical, "drive");
    case "mnt-drive-alias":
      return windowsPiDriveAlias(canonical, "mnt");
    case "cygdrive-alias":
      return windowsPiDriveAlias(canonical, "cygdrive");
  }
}

function passThroughPackageTarget(name: string, fixture: PiGuardFixture): string {
  switch (name) {
    case "ordinary":
      return path.join(fixture.root, "ordinary.txt");
    case "sibling-prefix":
      return path.join(fixture.siblingDir, "index.ts");
    case "literal-at":
      return "@my-file.txt";
    case "internal-url":
      return "agent://fixture/resource";
    case "malformed-file-url":
      return "file://%";
    case "package-read":
      return path.join(fixture.packageDir, "index.ts");
    default:
      throw new Error(`Unknown pass-through target: ${name}`);
  }
}

/** Stages the rendered template as a native package inside this workspace so its host imports still resolve. */
async function stageLoadedPackage(registerForCleanup = true): Promise<string> {
  const packageDir = await mkdtemp(path.join(import.meta.dir, ".loaded-package-"));
  if (registerForCleanup) temporaryRoots.push(packageDir);
  try {
    await writeFile(path.join(packageDir, "index.ts"), await readFile(STAGED_PATH, "utf8"), "utf8");
    await writeFile(path.join(packageDir, "package.json"), JSON.stringify({ name: "pi-slopgate", type: "module" }), "utf8");
    return packageDir;
  } catch (error) {
    await rm(packageDir, { recursive: true, force: true });
    throw error;
  }
}
const environmentSnapshot = new Map<string, string | undefined>();

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

function configureFake(response: unknown = {}): void {
  process.env.SLOPGATE_BIN = FAKE_ENFORCER;
  process.env.SLOPGATE_PI_FAKE_MODE = "response";
  process.env.SLOPGATE_PI_FAKE_RESPONSE = JSON.stringify(response);
  delete process.env.SLOPGATE_PI_FAKE_REAL_BIN;
  delete process.env.SLOPGATE_PI_FAKE_EXIT_CODE;
  delete process.env.SLOPGATE_PI_CHILD_PID_PATH;
  delete process.env.SLOPGATE_SESSION_ID;
}

async function createProject(root: string, name: string, managed = true): Promise<{ cwd: string; recordPath: string }> {
  const cwd = path.join(root, name);
  const recordPath = path.join(root, `${name}-enforcer.jsonl`);
  await mkdir(cwd, { recursive: true });
  await writeFile(recordPath, "", "utf8");
  if (managed) await writeFile(path.join(cwd, "slopgate.toml"), "[slopgate]\nenabled = true\n", "utf8");
  return { cwd, recordPath };
}

async function createHarness(
  cwd: string,
  recordPath: string,
  extensionPath: string = STAGED_PATH,
): Promise<PiRuntimeHarness> {
  const messages: unknown[] = [];
  const modelRuntime = await ModelRuntime.create({ allowModelNetwork: false, refreshOnCreate: false });
  const registry = new ModelRegistry(modelRuntime);
  process.env.SLOPGATE_BIN = FAKE_ENFORCER;
  process.env.SLOPGATE_PI_RECORD_PATH = recordPath;
  const loaded = await discoverAndLoadExtensions(
    [extensionPath],
    cwd,
    path.join(cwd, ".pi", "agent"),
    createEventBus(),
  );
  if (loaded.errors.length > 0 || loaded.extensions.length !== 1) {
    throw new Error(`Pi extension load failed: ${JSON.stringify(loaded.errors)}`);
  }
  const sessionManager = SessionManager.inMemory(cwd, { id: "native-pi-session" });
  const runner = new ExtensionRunner(loaded.extensions, loaded.runtime, cwd, sessionManager, registry);
  runner.bindCore(fakeActions(messages), fakeContextActions());
  return { runner, sessionManager, messages, cwd, recordPath };
}

async function readRecords(recordPath: string): Promise<Record<string, unknown>[]> {
  const contents = await readFile(recordPath, "utf8");
  return contents.split(/\r?\n/).filter(Boolean).map((line) => JSON.parse(line) as Record<string, unknown>);
}

async function withHarness(
  callback: (harness: PiRuntimeHarness) => Promise<void>,
  options: { managed?: boolean } = {},
): Promise<void> {
  const root = await mkdtemp(path.join(tmpdir(), "slopgate-pi-contract-"));
  temporaryRoots.push(root);
  const project = await createProject(root, "project", options.managed !== false);
  configureFake();
  process.env.SLOPGATE_PI_RECORD_PATH = project.recordPath;
  const harness = await createHarness(project.cwd, project.recordPath);
  await callback(harness);
}

function setResponse(response: unknown): void {
  process.env.SLOPGATE_PI_FAKE_MODE = "response";
  process.env.SLOPGATE_PI_FAKE_RESPONSE = JSON.stringify(response);
  delete process.env.SLOPGATE_PI_FAKE_REAL_BIN;
}

function setMode(mode: string): void {
  process.env.SLOPGATE_PI_FAKE_MODE = mode;
  delete process.env.SLOPGATE_PI_FAKE_REAL_BIN;
}

function turnEndEvent(turnIndex: number, text: string): TurnEndEvent {
  const message = {
    role: "assistant" as const,
    content: [{ type: "text" as const, text }],
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
    stopReason: "stop" as const,
    timestamp: turnIndex,
  };
  return { type: "turn_end", turnIndex, message, toolResults: [] };
}

async function preparePrompt(
  runner: ExtensionRunner,
  cwd: string,
  prompt: string,
  systemPrompt = "unchanged base system prompt",
) {
  return runner.emitBeforeAgentStart(prompt, undefined, systemPrompt, { cwd });
}

function textContents(content: { type: string; text?: string }[] | undefined): string[] {
  return (content ?? []).flatMap((part) => typeof part.text === "string" ? [part.text] : []);
}

function countOccurrences(value: string, fragment: string): number {
  return value.split(fragment).length - 1;
}

function recordsForEvent(records: Record<string, unknown>[], eventName: string): Record<string, unknown>[] {
  return records.filter((record) => record.hook_event_name === eventName);
}

function waitForRecordCount(recordPath: string, count: number): Promise<void> {
  const { promise, resolve, reject } = Promise.withResolvers<void>();
  let finished = false;
  const watcher = watchDirectory(path.dirname(recordPath), (_event, filename) => {
    if (filename?.toString() !== path.basename(recordPath)) return;
    void readRecords(recordPath).then((records) => {
      if (records.length < count || finished) return;
      finished = true;
      watcher.close();
      resolve();
    }, reject);
  });
  void readRecords(recordPath).then((records) => {
    if (records.length >= count && !finished) {
      finished = true;
      watcher.close();
      resolve();
    }
  }, reject);
  return promise;
}

function waitForFile(filePath: string): Promise<void> {
  const { promise, resolve, reject } = Promise.withResolvers<void>();
  let finished = false;
  const watcher = watchDirectory(path.dirname(filePath), (_event, filename) => {
    if (filename?.toString() !== path.basename(filePath) || finished) return;
    finished = true;
    watcher.close();
    resolve();
  });
  void readFile(filePath).then(() => {
    if (finished) return;
    finished = true;
    watcher.close();
    resolve();
  }, (error: NodeJS.ErrnoException) => {
    if (error.code !== "ENOENT") reject(error);
  });
  return promise;
}

async function processState(pidPath: string): Promise<string | undefined> {
  const pid = Number(await readFile(pidPath, "utf8"));
  try {
    const stat = await readFile(`/proc/${pid}/stat`, "utf8");
    return stat.slice(stat.lastIndexOf(")") + 2).split(" ", 1)[0];
  } catch {
    return undefined;
  }
}

beforeEach(() => {
  for (const key of ENVIRONMENT_KEYS) environmentSnapshot.set(key, process.env[key]);
});

afterEach(async () => {
  await Promise.all(temporaryRoots.splice(0).map((root) => rm(root, { recursive: true, force: true })));
  for (const key of ENVIRONMENT_KEYS) {
    const value = environmentSnapshot.get(key);
    if (value === undefined) delete process.env[key];
    else process.env[key] = value;
  }
  environmentSnapshot.clear();
});

describe("native Pi extension contract", () => {
  test("prepares bounded system context without persistent messages and consumes only matching revisions", async () => {
    await withHarness(async ({ runner, cwd, messages, recordPath }) => {
      setResponse({ context: "SESSION_CONTEXT_TOKEN" });
      await runner.emit({ type: "session_start", reason: "startup" });

      setResponse({ context: "IGNORED_REPLAY_CONTEXT" });
      await runner.emit({ type: "session_start", reason: "reload" });
      expect(recordsForEvent(await readRecords(recordPath), "session_start")).toHaveLength(1);

      setResponse({ context: "FIRST_PROMPT_CONTEXT" });
      await runner.emitInput("first prompt", undefined, "interactive");
      const basePrompt = "unchanged base system prompt";
      const first = await preparePrompt(runner, cwd, "first prompt", basePrompt);
      const second = await preparePrompt(runner, cwd, "first prompt", basePrompt);
      for (const prepared of [first, second]) {
        const systemPrompt = prepared?.systemPrompt || "";
        expect(systemPrompt.slice(0, basePrompt.length)).toBe(basePrompt);
        expect(systemPrompt).toContain("SESSION_CONTEXT_TOKEN");
        expect(systemPrompt).toContain("FIRST_PROMPT_CONTEXT");
        expect(countOccurrences(systemPrompt, "Slopgate hook context for this turn:")).toBe(1);
        expect(prepared?.messages ?? []).toEqual([]);
      }
      expect((await readRecords(recordPath)).map((record) => record.hook_event_name)).toEqual([
        "session_start",
        "input",
      ]);
      expect(messages).toEqual([]);

      setResponse({ context: "UI_COMMAND_CONTEXT" });
      await runner.emitInput("/settings", undefined, "interactive");
      setResponse({ context: "REAL_PROMPT_CONTEXT" });
      await runner.emitInput("real prompt after settings", undefined, "interactive");
      const afterSettings = await preparePrompt(runner, cwd, "real prompt after settings", basePrompt);
      expect(afterSettings?.systemPrompt).toContain("REAL_PROMPT_CONTEXT");
      expect(afterSettings?.systemPrompt).not.toContain("UI_COMMAND_CONTEXT");
      expect(afterSettings?.messages ?? []).toEqual([]);

      setResponse({ context: "TURN_GUIDANCE_TOKEN" });
      await runner.emit(turnEndEvent(1, "turn result"));
      const turnEndRecords = recordsForEvent(await readRecords(recordPath), "turn_end");
      expect(turnEndRecords[0]?.stop_response, "turn_end preserves the native message text").toBe("turn result");
      const guidancePreparationA = await preparePrompt(runner, cwd, "next prompt", basePrompt);
      const guidancePreparationB = await preparePrompt(runner, cwd, "next prompt", basePrompt);
      for (const prepared of [guidancePreparationA, guidancePreparationB]) {
        expect(prepared?.systemPrompt).toContain("TURN_GUIDANCE_TOKEN");
        expect(countOccurrences(prepared?.systemPrompt || "", "TURN_GUIDANCE_TOKEN")).toBe(1);
      }
      setResponse({});
      await runner.emit(turnEndEvent(2, "second response"));
      const afterConsumption = await preparePrompt(runner, cwd, "following prompt", basePrompt);
      expect(afterConsumption?.systemPrompt).not.toContain("TURN_GUIDANCE_TOKEN");
      setResponse({ context: "AGENT_END_GUIDANCE" });
      await runner.emit({ type: "agent_end", messages: [] });
      const agentEndPreparation = await preparePrompt(runner, cwd, "after agent end", basePrompt);
      expect(agentEndPreparation?.systemPrompt).toContain("AGENT_END_GUIDANCE");
      setResponse({});
      await runner.emit(turnEndEvent(3, "agent-end guidance consumed"));


      setResponse({ context: "OLDER_PROMPT_REVISION" });
      await runner.emitInput("older prompt", undefined, "interactive");
      await preparePrompt(runner, cwd, "older prompt", basePrompt);
      setResponse({ context: "NEWER_PROMPT_REVISION" });
      await runner.emitInput("newer prompt", undefined, "interactive");
      setResponse({});
      await runner.emit(turnEndEvent(4, "older request completed"));
      const newestPreparation = await preparePrompt(runner, cwd, "newer prompt", basePrompt);
      expect(newestPreparation?.systemPrompt).toContain("NEWER_PROMPT_REVISION");
      expect(newestPreparation?.systemPrompt).not.toContain("OLDER_PROMPT_REVISION");
      const inspectedContexts: string[] = [];
      const ui = runner.getUIContext();
      ui.editor = async (_title, content) => {
        inspectedContexts.push(content || "");
        return undefined;
      };
      runner.setUIContext(ui, "tui");
      const contextCommand = runner.getCommand("slopgate-context");
      if (!contextCommand) throw new Error("Slopgate context command was not registered");
      await contextCommand.handler("", runner.createCommandContext());
      expect(inspectedContexts).toHaveLength(1);
      expect(inspectedContexts[0]).toContain("SESSION_CONTEXT_TOKEN");
      expect(inspectedContexts[0]).toContain("NEWER_PROMPT_REVISION");
      expect(inspectedContexts[0]).not.toContain("OLDER_PROMPT_REVISION");

      expect(recordsForEvent(await readRecords(recordPath), "session_start")).toHaveLength(1);
      expect(messages).toEqual([]);
    });
  });
  test.each([
    ["text", { text: "rewritten input" }, "rewritten input"],
    ["prompt", { prompt: "rewritten prompt" }, "rewritten prompt"],
  ] as const)("transforms input from updated_input.%s", async (_field, updatedInput, text) => {
    await withHarness(async ({ runner }) => {
      setResponse({ updated_input: updatedInput });
      const result = await runner.emitInput("original input", undefined, "interactive");
      expect(result, "updated input becomes the native transform result").toEqual({ action: "transform", text });
    });
  });

  test("applies tool_call updated_input to the native event consumed by Pi", async () => {
    await withHarness(async ({ runner }) => {
      setResponse({ updated_input: { path: "rewritten.txt", content: "rewritten" } });
      const input = { path: "original.txt", content: "original" };
      await runner.emitToolCall({
        type: "tool_call",
        toolCallId: "updated-input-write",
        toolName: "write",
        input,
      });
      expect(input, "the runner's native tool input receives the rewrite").toEqual({
        path: "rewritten.txt",
        content: "rewritten",
      });
    });
  });


  test("merges pre-tool and post-tool findings into one native result and evaluates only tool_result", async () => {
    await withHarness(async ({ runner, messages, recordPath }) => {
      setResponse({ context: "PRE_TOOL_REPAIR_CONTEXT" });
      await runner.emitToolCall({
        type: "tool_call",
        toolCallId: "repair-success",
        toolName: "read",
        input: { path: "README.md" },
      });

      setResponse({
        context: "POST_TOOL_REPAIR_CONTEXT",
        reason: "POST_TOOL_REPAIR_CONTEXT",
        tool_result_patch: {
          details: { slopgate: { decision: "context", rule: "REPAIR_REQUIRED_TOKEN" } },
          isError: true,
        },
      });
      const successfulEvent: ToolResultEvent = {
        type: "tool_result",
        toolCallId: "repair-success",
        toolName: "custom_tool",
        input: { path: "README.md" },
        content: [
          { type: "text", text: "original tool output" },
          { type: "image", data: "aW1hZ2U=", mimeType: "image/png" },
        ],
        details: { unrelated: { preserved: true } },
        isError: false,
      };
      const successPatch = await runner.emitToolResult(successfulEvent);
      expect(successPatch?.content).toHaveLength(3);
      expect(successPatch?.content?.[0]).toEqual(successfulEvent.content[0]);
      expect(successPatch?.content?.[1]).toEqual(successfulEvent.content[1]);
      const successText = textContents(successPatch?.content).join("\n");
      expect(successText).toContain("original tool output");
      expect(successText).toContain("Slopgate findings:\n");
      expect(successText).toContain("PRE_TOOL_REPAIR_CONTEXT");
      expect(successText).toContain("POST_TOOL_REPAIR_CONTEXT");
      expect(countOccurrences(successText, "POST_TOOL_REPAIR_CONTEXT")).toBe(1);
      expect(successPatch?.details).toEqual({
        unrelated: { preserved: true },
        slopgate: { decision: "context", rule: "REPAIR_REQUIRED_TOKEN" },
      });
      expect(successPatch?.isError).toBe(true);

      const toolEnd: ToolExecutionEndEvent = {
        type: "tool_execution_end",
        toolCallId: "repair-success",
        toolName: "custom_tool",
        result: "done",
        isError: false,
      };
      const recordCountBeforeNotification = (await readRecords(recordPath)).length;
      await runner.emit(toolEnd);
      expect(await readRecords(recordPath)).toHaveLength(recordCountBeforeNotification);
      expect(recordsForEvent(await readRecords(recordPath), "tool_result").filter(
        (record) => record.tool_call_id === "repair-success",
      )).toHaveLength(1);
      expect(messages).toEqual([]);

      setResponse({
        context: "FAILURE_FINDING",
        tool_result_patch: { isError: false, details: { slopgate: { rule: "failure" } } },
      });
      const failedEvent: ToolResultEvent = {
        type: "tool_result",
        toolCallId: "repair-failure",
        toolName: "custom_tool",
        input: {},
        content: [{ type: "text", text: "failed output" }],
        details: { exitCode: 2, unrelated: "kept" },
        isError: true,
      };
      const failurePatch = await runner.emitToolResult(failedEvent);
      expect(failurePatch?.isError).toBe(false);
      expect(failurePatch?.details).toEqual({
        exitCode: 2,
        unrelated: "kept",
        slopgate: { rule: "failure" },
      });
      expect(textContents(failurePatch?.content).join("\n")).toContain("FAILURE_FINDING");
      const failurePayload = (await readRecords(recordPath)).find(
        (record) => record.hook_event_name === "tool_result" && record.tool_call_id === "repair-failure",
      );
      expect(failurePayload).toMatchObject({ isError: true, details: { exitCode: 2 } });

      setResponse({ reason: "NATIVE_ERROR_STATE_PRESERVED" });
      const absentPatchEvent: ToolResultEvent = {
        type: "tool_result",
        toolCallId: "repair-no-iserror-patch",
        toolName: "custom_tool",
        input: {},
        content: [{ type: "text", text: "native failure" }],
        details: { exit_code: 9 },
        isError: true,
      };
      const absentPatch = await runner.emitToolResult(absentPatchEvent);
      expect(absentPatch?.isError).toBe(true);
      expect(absentPatch?.details).toEqual({ exit_code: 9 });
      expect((await readRecords(recordPath)).find(
        (record) => record.tool_call_id === "repair-no-iserror-patch",
      )).toMatchObject({ isError: true, details: { exit_code: 9 } });

      setResponse({ context: "PRE_TOOL_ONLY_CONTEXT" });
      await runner.emitToolCall({
        type: "tool_call",
        toolCallId: "repair-pre-only",
        toolName: "read",
        input: { path: "README.md" },
      });
      setMode("empty");
      const preOnlyEvent: ToolResultEvent = {
        type: "tool_result",
        toolCallId: "repair-pre-only",
        toolName: "custom_tool",
        input: {},
        content: [{ type: "text", text: "original without post-tool findings" }],
        details: { audit: "preserved" },
        isError: false,
      };
      const preOnlyPatch = await runner.emitToolResult(preOnlyEvent);
      expect(preOnlyPatch?.details).toEqual({ audit: "preserved" });
      expect(textContents(preOnlyPatch?.content).join("\n")).toContain("PRE_TOOL_ONLY_CONTEXT");
      const duplicateResult = await runner.emitToolResult(preOnlyEvent);
      const duplicateText = textContents(duplicateResult?.content).join("\n");
      expect(duplicateText).toContain("original without post-tool findings");
      expect(duplicateText).not.toContain("PRE_TOOL_ONLY_CONTEXT");
      expect(duplicateResult?.details).toEqual({ audit: "preserved" });
      expect(messages).toEqual([]);
    });
  });

  test("native denial channels remain intact for headless and interactive input and user Bash", async () => {
    await withHarness(async ({ runner, messages }) => {
      const diagnostics: string[] = [];
      const originalConsoleError = console.error;
      console.error = (...values: unknown[]) => diagnostics.push(values.map(String).join(" "));
      try {
        setResponse({ block: true, reason: "INPUT_DENIED_TOKEN" });
        const headlessResult = await runner.emitInput("blocked prompt", undefined, "interactive");
        expect(headlessResult).toEqual({ action: "handled" });
        expect(diagnostics).toEqual(["[slopgate] input blocked: INPUT_DENIED_TOKEN"]);

        const notices: string[] = [];
        const ui = runner.getUIContext();
        ui.notify = (message) => notices.push(message);
        runner.setUIContext(ui, "tui");
        setResponse({ block: true, reason: "INTERACTIVE_INPUT_DENIED" });
        const interactiveResult = await runner.emitInput("another blocked prompt", undefined, "interactive");
        expect(interactiveResult).toEqual({ action: "handled" });
        expect(notices).toEqual(["INTERACTIVE_INPUT_DENIED"]);
        expect(diagnostics).toHaveLength(1);

        setResponse({ block: true, reason: "TOOL_CALL_DENIED" });
        const toolCallResult = await runner.emitToolCall({
          type: "tool_call",
          toolCallId: "blocked-tool-call",
          toolName: "read",
          input: { path: "README.md" },
        });
        expect(toolCallResult).toEqual({ block: true, reason: "TOOL_CALL_DENIED" });

        setResponse({ block: true, reason: "USER_BASH_DENIED" });
        const userBashEvent: UserBashEvent = {
          type: "user_bash",
          command: "printf blocked",
          excludeFromContext: false,
          cwd: process.cwd(),
        };
        const userBashResult = await runner.emitUserBash(userBashEvent);
        expect(userBashResult?.result).toEqual({
          output: "USER_BASH_DENIED",
          exitCode: 1,
          cancelled: false,
          truncated: false,
        });
        expect(messages).toEqual([]);
      } finally {
        console.error = originalConsoleError;
      }
    });
  });

  test("native session identities and separate extension factories keep context isolated", async () => {
    const rootA = await mkdtemp(path.join(tmpdir(), "slopgate-pi-session-a-"));
    const rootB = await mkdtemp(path.join(tmpdir(), "slopgate-pi-session-b-"));
    temporaryRoots.push(rootA, rootB);
    const projectA = await createProject(rootA, "project-a");
    const projectB = await createProject(rootB, "project-b");
    configureFake();
    const harnessA = await createHarness(projectA.cwd, projectA.recordPath);
    const harnessB = await createHarness(projectB.cwd, projectB.recordPath);

    process.env.SLOPGATE_PI_RECORD_PATH = projectA.recordPath;
    setResponse({ context: "SESSION_A_CONTEXT" });
    await harnessA.runner.emit({ type: "session_start", reason: "startup" });
    harnessA.sessionManager.newSession({ id: "native-session-b" });
    process.env.SLOPGATE_PI_RECORD_PATH = projectA.recordPath;
    setResponse({ context: "SESSION_B_CONTEXT" });
    await harnessA.runner.emit({ type: "session_start", reason: "new" });
    const sessionBPrompt = await preparePrompt(harnessA.runner, projectA.cwd, "prompt B");
    expect(sessionBPrompt?.systemPrompt).toContain("SESSION_B_CONTEXT");
    expect(sessionBPrompt?.systemPrompt).not.toContain("SESSION_A_CONTEXT");
    setResponse({ context: "NAVIGATION_GUIDANCE" });
    await harnessA.runner.emit(turnEndEvent(1, "session B response"));
    const guidedPrompt = await preparePrompt(harnessA.runner, projectA.cwd, "guided B prompt");
    expect(guidedPrompt?.systemPrompt).toContain("NAVIGATION_GUIDANCE");
    await harnessA.runner.emit({
      type: "session_tree",
      newLeafId: "new-leaf",
      oldLeafId: "old-leaf",
    });
    const navigatedPrompt = await preparePrompt(harnessA.runner, projectA.cwd, "navigated B prompt");
    expect(navigatedPrompt?.systemPrompt).not.toContain("NAVIGATION_GUIDANCE");
    expect(navigatedPrompt?.systemPrompt).toContain("SESSION_B_CONTEXT");


    harnessA.sessionManager.newSession({ id: "native-pi-session" });
    setResponse({ context: "SHOULD_NOT_REEVALUATE_SESSION_A" });
    await harnessA.runner.emit({ type: "session_start", reason: "resume" });
    const resumedAPrompt = await preparePrompt(harnessA.runner, projectA.cwd, "prompt A");
    expect(resumedAPrompt?.systemPrompt).toContain("SESSION_A_CONTEXT");
    expect(resumedAPrompt?.systemPrompt).not.toContain("SESSION_B_CONTEXT");
    expect(recordsForEvent(await readRecords(projectA.recordPath), "session_start")).toHaveLength(2);

    process.env.SLOPGATE_PI_RECORD_PATH = projectB.recordPath;
    setResponse({ context: "FACTORY_B_CONTEXT" });
    await harnessB.runner.emit({ type: "session_start", reason: "startup" });
    const factoryAPrompt = await preparePrompt(harnessA.runner, projectA.cwd, "factory A");
    const factoryBPrompt = await preparePrompt(harnessB.runner, projectB.cwd, "factory B");
    expect(factoryAPrompt?.systemPrompt).toContain("SESSION_A_CONTEXT");
    expect(factoryAPrompt?.systemPrompt).not.toContain("FACTORY_B_CONTEXT");
    expect(factoryBPrompt?.systemPrompt).toContain("FACTORY_B_CONTEXT");
    expect(harnessA.messages).toEqual([]);
    expect(harnessB.messages).toEqual([]);
  });

  test("the real Python adapter accepts the compact payload and pre-tool advice survives a null result", async () => {
    await withHarness(async ({ runner, cwd, recordPath }) => {
      const root = path.dirname(cwd);
      const isolatedHome = path.join(root, "home");
      const configDir = path.join(root, "config");
      const stateRoot = path.join(root, "state");
      await Promise.all([
        mkdir(isolatedHome, { recursive: true }),
        mkdir(configDir, { recursive: true }),
        mkdir(stateRoot, { recursive: true }),
      ]);
      process.env.HOME = isolatedHome;
      process.env.XDG_CONFIG_HOME = path.join(isolatedHome, ".config");
      process.env.XDG_DATA_HOME = path.join(isolatedHome, ".local/share");
      process.env.XDG_STATE_HOME = path.join(isolatedHome, ".local/state");
      process.env.XDG_CACHE_HOME = path.join(isolatedHome, ".cache");
      process.env.SLOPGATE_CONFIG_DIR = configDir;
      process.env.SLOPGATE_ROOT = stateRoot;
      process.env.SLOPGATE_DAEMON_SOCKET = path.join(root, "unbound-daemon.sock");
      process.env.SLOPGATE_PI_RECORD_PATH = recordPath;
      process.env.SLOPGATE_PI_FAKE_REAL_BIN = REAL_SLOPGATE;
      delete process.env.SLOPGATE_PI_FAKE_RESPONSE;

      await runner.emit({ type: "session_start", reason: "startup" });
      setResponse({ context: "REAL_ADAPTER_PRE_TOOL_ADVICE" });
      await runner.emitToolCall({
        type: "tool_call",
        toolCallId: "real-adapter-result",
        toolName: "read",
        input: { path: "README.md" },
      });

      process.env.SLOPGATE_PI_FAKE_REAL_BIN = REAL_SLOPGATE;
      const event: ToolResultEvent = {
        type: "tool_result",
        toolCallId: "real-adapter-result",
        toolName: "custom_tool",
        input: {},
        content: [{ type: "text", text: "normal result" }],
        details: { exitCode: 0, unrelated: "kept" },
        isError: false,
      };
      const nativePatch = await runner.emitToolResult(event);
      expect(nativePatch).toEqual({
        content: [
          { type: "text", text: "normal result" },
          { type: "text", text: "Slopgate findings:\nREAL_ADAPTER_PRE_TOOL_ADVICE" },
        ],
        details: { exitCode: 0, unrelated: "kept" },
        isError: false,
      });

      const payload = (await readRecords(recordPath)).find(
        (record) => record.hook_event_name === "tool_result" && record.tool_call_id === "real-adapter-result",
      );
      expect(payload).toMatchObject({
        hook_event_name: "tool_result",
        isError: false,
        details: { exitCode: 0, unrelated: "kept" },
      });
      expect(payload).toHaveProperty("tool_result");
      expect(payload).not.toHaveProperty("tool_response");
      expect(payload).not.toHaveProperty("pi_event");
    });
  }, 30_000);

  test("enforcer timeout, lost stdin, invalid output, nonzero exit, empty success, and shutdown cancellation are bounded", async () => {
    await withHarness(async ({ runner, recordPath }) => {
      const diagnostics: string[] = [];
      const originalConsoleError = console.error;
      console.error = (...values: unknown[]) => diagnostics.push(values.map(String).join(" "));
      const childPidPath = path.join(path.dirname(recordPath), "grandchild.pid");
      try {
        setMode("invalid");
        const invalid = await runner.emitToolCall({
          type: "tool_call",
          toolCallId: "invalid-json",
          toolName: "read",
          input: { path: "README.md" },
        });
        expect(invalid?.block).toBe(true);
        expect(invalid?.reason).toContain("invalid JSON");

        setMode("nonzero");
        const nonzero = await runner.emitToolCall({
          type: "tool_call",
          toolCallId: "nonzero-exit",
          toolName: "read",
          input: { path: "README.md" },
        });
        expect(nonzero?.block).toBe(true);
        expect(diagnostics.join("\n")).not.toContain("PRIVATE_CHILD_STDERR");

        setMode("empty");
        const empty = await runner.emitToolCall({
          type: "tool_call",
          toolCallId: "empty-success",
          toolName: "read",
          input: { path: "README.md" },
        });
        expect(empty).toBeUndefined();

        setMode("early-exit");
        const lostInput = await runner.emitToolCall({
          type: "tool_call",
          toolCallId: "lost-input",
          toolName: "read",
          input: { path: `sensitive-${"x".repeat(4 * 1024 * 1024)}` },
        });
        expect(lostInput?.block).toBe(true);
        expect(lostInput?.reason).toContain("did not read its input");
        expect(diagnostics.join("\n")).not.toContain("sensitive-");

        setMode("hang");
        process.env.SLOPGATE_ENFORCER_TIMEOUT_MS = "1000";
        process.env.SLOPGATE_PI_CHILD_PID_PATH = childPidPath;
        const timeoutBarrier = waitForFile(childPidPath);
        const timedOutPromise = runner.emitToolCall({
          type: "tool_call",
          toolCallId: "timeout",
          toolName: "read",
          input: { path: "README.md" },
        });
        await timeoutBarrier;
        const timedOut = await timedOutPromise;
        expect(timedOut?.block).toBe(true);
        expect(timedOut?.reason).toContain("timed out");
        expect(diagnostics.join("\n")).toContain('"category":"timeout"');
        if (process.platform === "linux") {
          const state = await processState(childPidPath);
          expect(state === undefined || state === "Z").toBe(true);
        }

        const shutdownChildPidPath = path.join(path.dirname(recordPath), "shutdown-grandchild.pid");
        process.env.SLOPGATE_PI_CHILD_PID_PATH = shutdownChildPidPath;
        process.env.SLOPGATE_ENFORCER_TIMEOUT_MS = "10000";
        const nextRecordCount = (await readRecords(recordPath)).length + 1;
        const shutdownBarrier = waitForRecordCount(recordPath, nextRecordCount);
        const pendingCall = runner.emitToolCall({
          type: "tool_call",
          toolCallId: "shutdown-cancel",
          toolName: "read",
          input: { path: "README.md" },
        });
        await shutdownBarrier;
        await waitForFile(shutdownChildPidPath);
        const diagnosticsBeforeShutdown = diagnostics.length;
        await runner.emit({ type: "session_shutdown", reason: "quit" });
        expect(await pendingCall).toBeUndefined();
        expect(diagnostics.slice(diagnosticsBeforeShutdown).join("\n")).not.toContain("timeout");
        expect(diagnostics.join("\n")).not.toContain("PRIVATE_CHILD_STDERR");
        if (process.platform === "linux") {
          const state = await processState(shutdownChildPidPath);
          expect(state === undefined || state === "Z").toBe(true);
        }
      } finally {
        console.error = originalConsoleError;
      }
    });
  }, 30_000);

  test("unmanaged enforcer failures remain no-op", async () => {
    const root = await mkdtemp(path.join(tmpdir(), "slopgate-pi-unmanaged-"));
    temporaryRoots.push(root);
    const project = await createProject(root, "unmanaged", false);
    configureFake();
    process.env.SLOPGATE_PI_RECORD_PATH = project.recordPath;
    const { runner } = await createHarness(project.cwd, project.recordPath);
    setMode("nonzero");
    const result = await runner.emitToolCall({
      type: "tool_call",
      toolCallId: "unmanaged-nonzero",
      toolName: "read",
      input: { path: "README.md" },
    });
    expect(result).toBeUndefined();
  });

  test("only Slopgate-owned paths are denied locally; ordinary project writes reach the enforcer", async () => {
    await withHarness(async ({ runner, recordPath }) => {
      setResponse({});
      const ordinary = await runner.emitToolCall({
        type: "tool_call",
        toolCallId: "ordinary-write",
        toolName: "write",
        input: { path: "src/app.py", content: "x = 1\n" },
      });
      expect(ordinary).toBeUndefined();
      const evaluated = await readRecords(recordPath);
      expect(evaluated.some((record) => record.tool_call_id === "ordinary-write")).toBe(true);

      const protectedWrite = await runner.emitToolCall({
        type: "tool_call",
        toolCallId: "protected-write",
        toolName: "write",
        input: { path: "slopgate.toml", content: "" },
      });
      expect(protectedWrite?.block).toBe(true);
      expect(protectedWrite?.reason).toContain("slopgate.toml");
      expect((await readRecords(recordPath)).some((record) => record.tool_call_id === "protected-write")).toBe(false);
    });
  });

  test("a cancelled tool_result adds no findings and settles its pre-tool context", async () => {
    await withHarness(async ({ runner, recordPath }) => {
      const childPidPath = path.join(path.dirname(recordPath), "result-cancel.pid");
      setResponse({ context: "PRE_TOOL_CANCEL_CONTEXT" });
      await runner.emitToolCall({
        type: "tool_call",
        toolCallId: "cancelled-result",
        toolName: "read",
        input: { path: "README.md" },
      });
      setMode("hang");
      process.env.SLOPGATE_PI_CHILD_PID_PATH = childPidPath;
      process.env.SLOPGATE_ENFORCER_TIMEOUT_MS = "10000";
      const barrier = waitForFile(childPidPath);
      const pending = runner.emitToolResult({
        type: "tool_result",
        toolCallId: "cancelled-result",
        toolName: "read",
        input: { path: "README.md" },
        content: [{ type: "text", text: "original output" }],
        details: undefined,
        isError: false,
      });
      await barrier;
      await runner.emit({ type: "session_shutdown", reason: "quit" });
      expect(await pending).toBeUndefined();
    });
  }, 30_000);

  test("enforcement continues for calls made after session_shutdown", async () => {
    await withHarness(async ({ runner }) => {
      await runner.emit({ type: "session_shutdown", reason: "new" });

      setResponse({ block: true, reason: "POST_SHUTDOWN_DENIED" });
      const result = await runner.emitToolCall({
        type: "tool_call",
        toolCallId: "after-shutdown",
        toolName: "read",
        input: { path: "README.md" },
      });

      expect(result).toEqual({ block: true, reason: "POST_SHUTDOWN_DENIED" });
    });
  });
  describe("loaded package path aliases", () => {
    let fixture: PiGuardFixture | undefined;
    let packageDir: string | undefined;
    let root: string | undefined;
    let siblingDir: string | undefined;
    const savedEnvironment = new Map<string, string | undefined>();

    function requireGuardFixture(): PiGuardFixture {
      if (fixture === undefined) throw new Error("Pi loaded-package guard fixture is unavailable");
      return fixture;
    }

    beforeAll(async () => {
      for (const key of ENVIRONMENT_KEYS) savedEnvironment.set(key, process.env[key]);
      process.env.HOME = import.meta.dir;
      process.env.USERPROFILE = import.meta.dir;
      const currentRoot = await mkdtemp(path.join(tmpdir(), "slopgate-pi-loaded-package-"));
      root = currentRoot;
      const currentPackageDir = await stageLoadedPackage(false);
      packageDir = currentPackageDir;
      const currentSiblingDir = `${currentPackageDir}-sibling`;
      siblingDir = currentSiblingDir;
      await mkdir(currentSiblingDir, { recursive: true });
      await writeFile(path.join(currentSiblingDir, "index.ts"), "sibling package", "utf8");
      const managedProject = await createProject(currentRoot, "managed", true);
      const unmanagedProject = await createProject(currentRoot, "unmanaged", false);
      const symlinkParent = path.join(currentRoot, "package-parent-link");
      if (process.platform === "win32") await symlink(currentPackageDir, symlinkParent, "junction");
      else await symlink(currentPackageDir, symlinkParent);
      const symlinkLeaves = new Map<PiPackageFile, string>();
      for (const file of PI_PACKAGE_FILES) {
        const link = path.join(currentRoot, `${file}.leaf-link`);
        await symlink(path.join(currentPackageDir, file), link);
        symlinkLeaves.set(file, link);
      }
      configureFake();
      const currentManagedHarness = await createHarness(
        managedProject.cwd,
        managedProject.recordPath,
        path.join(currentPackageDir, "index.ts"),
      );
      const currentUnmanagedHarness = await createHarness(
        unmanagedProject.cwd,
        unmanagedProject.recordPath,
        path.join(currentPackageDir, "index.ts"),
      );
      fixture = {
        managedHarness: currentManagedHarness,
        unmanagedHarness: currentUnmanagedHarness,
        packageDir: currentPackageDir,
        root: currentRoot,
        siblingDir: currentSiblingDir,
        symlinkParent,
        symlinkLeaves,
      };
    });

    afterAll(async () => {
      for (const key of ENVIRONMENT_KEYS) {
        const value = savedEnvironment.get(key);
        if (value === undefined) delete process.env[key];
        else process.env[key] = value;
      }
      const ownedRoots = [packageDir, root, siblingDir].filter((ownedRoot): ownedRoot is string => ownedRoot !== undefined);
      await Promise.all(ownedRoots.map((ownedRoot) => rm(ownedRoot, { recursive: true, force: true })));
    });

    test.each(PI_PACKAGE_GUARD_CASES)(
      "blocks writes and edits from %s cwd via %s alias for %s",
      async (scope, alias, file) => {
        const current = requireGuardFixture();
        const harness = guardHarness(scope, current);
        const target = packageTargetForAlias(alias, file, guardCwd(scope, current), current);
        process.env.SLOPGATE_PI_RECORD_PATH = harness.recordPath;
        setResponse({});
        const writeResult = await harness.runner.emitToolCall({
          type: "tool_call",
          toolCallId: `loaded-package-write-${scope}-${alias}-${file}`,
          toolName: "write",
          input: { path: target, content: "tampered" },
        });
        expect(writeResult?.block, "host-equivalent package writes are refused").toBe(true);
        expect(writeResult?.reason, "the refusal attributes the original target").toContain(target);

        const editResult = await harness.runner.emitToolCall({
          type: "tool_call",
          toolCallId: `loaded-package-edit-${scope}-${alias}-${file}`,
          toolName: "edit",
          input: { path: target, oldText: "before", newText: "after" },
        });
        expect(editResult?.block, "host-equivalent package edits are refused").toBe(true);
        expect(editResult?.reason, "the edit refusal attributes the original target").toContain(target);
      },
      30_000,
    );

    test.each(PI_PASS_THROUGH_CASES)(
      "does not deny %s cwd target %s via %s",
      async (scope, targetName, toolName) => {
        const current = requireGuardFixture();
        const harness = guardHarness(scope, current);
        const target = passThroughPackageTarget(targetName, current);
        const toolCallId = `package-pass-through-${scope}-${targetName}`;
        process.env.SLOPGATE_PI_RECORD_PATH = harness.recordPath;
        setResponse({});
        const result = await harness.runner.emitToolCall({
          type: "tool_call",
          toolCallId,
          toolName,
          input: { path: target, content: "unchanged" },
        });
        expect(result?.block, `${targetName} is not denied by package containment`).not.toBe(true);
        const records = await readRecords(harness.recordPath);
        expect(records.some((record) => record.tool_call_id === toolCallId), `${targetName} reaches the enforcer`).toBe(true);
      },
      30_000,
    );

    test.each(PI_GUARD_SCOPES)("keeps slopgate.toml repo-gated from %s cwd", async (scope) => {
      const current = requireGuardFixture();
      const harness = guardHarness(scope, current);
      const toolCallId = `package-config-${scope}`;
      process.env.SLOPGATE_PI_RECORD_PATH = harness.recordPath;
      setResponse({});
      const result = await harness.runner.emitToolCall({
        type: "tool_call",
        toolCallId,
        toolName: "write",
        input: { path: "slopgate.toml", content: "" },
      });
      if (scope === "managed") {
        expect(result?.block, "managed projects retain local infrastructure protection").toBe(true);
        expect(result?.reason, "the managed refusal attributes slopgate.toml").toContain("slopgate.toml");
      } else {
        expect(result?.block, "unmanaged cwd does not acquire repo-local protection").not.toBe(true);
        const records = await readRecords(harness.recordPath);
        expect(records.some((record) => record.tool_call_id === toolCallId), "unmanaged writes reach the enforcer").toBe(true);
      }
    }, 30_000);
  });
});
