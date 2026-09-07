/**
 * Loads an installed OMP Slopgate extension artifact through the pinned native
 * ExtensionRunner and proves guard/enforcer behavior on the installed bytes.
 *
 * Usage: bun run scripts/load-installed.ts <installed-index.ts> <managed-cwd> <record-path>
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
	process.stderr.write("Usage: bun run scripts/load-installed.ts <absolute-index.ts> <absolute-cwd> <absolute-record-path>\n");
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

const scratch = await mkdtemp(path.join(tmpdir(), "slopgate-omp-installed-"));
try {
	const authStorage = await AuthStorage.create(path.join(scratch, "auth.db"));
	const modelRegistry = new ModelRegistry(authStorage, path.join(scratch, "models.yml"), {
		cacheDbPath: path.join(scratch, "models-cache.db"),
		ignoreLocalModelConfig: true,
	});
	const sessionManager = SessionManager.inMemory(projectCwd);
	const runtime = new ExtensionRuntime();
	const installedModule: { default: ExtensionFactory } = await import(pathToFileURL(indexPath).href);
	const factory = installedModule.default;
	const extension = await loadExtensionFromFactory(factory, projectCwd, new EventBus(), runtime, "slopgate-installed");
	const runner = new ExtensionRunner([extension], runtime, projectCwd, sessionManager, modelRegistry);
	const actions = {
		sendMessage: () => {},
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
		getSystemPrompt: () => "",
	} satisfies ExtensionContextActions;
	runner.initialize(actions, contextActions);

	function requireBlock(
		result: { readonly block?: boolean; readonly reason?: string } | undefined,
		label: string,
	): string {
		if (!result?.block || typeof result.reason !== "string" || !result.reason.includes("slopgate.toml")) {
			throw new Error(`Installed artifact did not block the protected target (${label}): ${JSON.stringify(result)}`);
		}
		return result.reason;
	}
	const writeReason = requireBlock(
		await runner.emitToolCall({
			type: "tool_call",
			toolCallId: "installed-write",
			toolName: "write",
			input: { path: "slopgate.toml", content: "blocked" },
		}),
		"write",
	);
	const hashlineReason = requireBlock(
		await runner.emitToolCall({
			type: "tool_call",
			toolCallId: "installed-hashline",
			toolName: "edit",
			input: { input: "[slopgate.toml#a1b2]\n+enabled = false" },
		}),
		"hashline",
	);
	const patchReason = requireBlock(
		await runner.emitToolCall({
			type: "tool_call",
			toolCallId: "installed-apply-patch",
			toolName: "edit",
			input: { input: "*** Begin Patch\n*** Update File: slopgate.toml\n@@\n-enabled = true\n+enabled = false\n*** End Patch" },
		}),
		"apply-patch",
	);
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

	process.stdout.write(`${JSON.stringify({
		blocked: { applyPatch: patchReason, hashline: hashlineReason, write: writeReason },
		extensions: 1,
		loaded: true,
		session: payload.session_id,
	})}\n`);
	await sessionManager.close();
	authStorage.close();
} finally {
	await rm(scratch, { force: true, recursive: true });
}
