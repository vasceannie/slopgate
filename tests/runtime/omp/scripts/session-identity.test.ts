import { strict as assert } from "node:assert";
import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { ModelRegistry } from "@oh-my-pi/pi-coding-agent/config/model-registry";
import { ExtensionRuntime, loadExtensionFromFactory } from "@oh-my-pi/pi-coding-agent/extensibility/extensions/loader";
import { ExtensionRunner } from "@oh-my-pi/pi-coding-agent/extensibility/extensions/runner";
import type { ExtensionFactory } from "@oh-my-pi/pi-coding-agent/extensibility/extensions/types";
import { AuthStorage } from "@oh-my-pi/pi-coding-agent/session/auth-storage";
import { SessionManager } from "@oh-my-pi/pi-coding-agent/session/session-manager";
import { EventBus } from "@oh-my-pi/pi-coding-agent/utils/event-bus";

type ObservedIdentity = {
  readonly event: "input" | "session_start" | "session_stop";
  readonly sessionId: string;
};

async function observeRunnerSession(modelRegistry: ModelRegistry): Promise<readonly ObservedIdentity[]> {
  const observations: ObservedIdentity[] = [];
  const factory: ExtensionFactory = (pi) => {
    pi.on("session_start", (_event, ctx) => {
      observations.push({ event: "session_start", sessionId: ctx.sessionManager.getSessionId() });
    });
    pi.on("input", (_event, ctx) => {
      observations.push({ event: "input", sessionId: ctx.sessionManager.getSessionId() });
    });
    pi.on("session_stop", (_event, ctx) => {
      observations.push({ event: "session_stop", sessionId: ctx.sessionManager.getSessionId() });
    });
  };
  const cwd = ".";
  const sessionManager = SessionManager.inMemory(cwd);
  const runtime = new ExtensionRuntime();
  const extension = await loadExtensionFromFactory(factory, cwd, new EventBus(), runtime, "identity-proof");
  const runner = new ExtensionRunner([extension], runtime, cwd, sessionManager, modelRegistry);

  await runner.emit({ type: "session_start" });
  await runner.emitInput("identity", undefined, "extension");
  await runner.emitSessionStop({
    messages: [],
    session_id: sessionManager.getSessionId(),
    signal: new AbortController().signal,
    stop_hook_active: false,
    turn_id: 1,
  });
  await sessionManager.close();
  return observations;
}

async function main(): Promise<void> {
  const root = await mkdtemp(join(tmpdir(), "slopgate-omp-identity-"));
  const authStorage = await AuthStorage.create(join(root, "auth.db"));
  try {
    const modelRegistry = new ModelRegistry(authStorage, join(root, "models.yml"), {
      cacheDbPath: join(root, "models-cache.db"),
      ignoreLocalModelConfig: true,
    });
    const first = await observeRunnerSession(modelRegistry);
    const second = await observeRunnerSession(modelRegistry);
    assert.deepEqual(
      first.map((observation) => observation.event),
      ["session_start", "input", "session_stop"],
      "runner must invoke all identity-observation listeners",
    );
    const firstId = first[0]?.sessionId;
    const secondId = second[0]?.sessionId;
    assert.ok(firstId, "first runner must expose a session id");
    assert.ok(secondId, "second runner must expose a session id");
    assert.ok(first.every((observation) => observation.sessionId === firstId), "session id must remain stable");
    assert.ok(second.every((observation) => observation.sessionId === secondId), "second session id must remain stable");
    assert.notEqual(firstId, secondId, "different runner sessions must expose distinct ids");
  } finally {
    authStorage.close();
    await rm(root, { force: true, recursive: true });
  }
}

await main();
