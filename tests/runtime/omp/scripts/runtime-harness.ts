import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
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
import type { BashToolInput } from "@oh-my-pi/pi-coding-agent/tools/bash";
import { EventBus } from "@oh-my-pi/pi-coding-agent/utils/event-bus";

type BashEffect = (input: BashToolInput) => Promise<void>;

export type BashExecutionOutcome =
	| { readonly kind: "blocked"; readonly reason: string }
	| { readonly kind: "executed"; readonly input: BashToolInput };

export class MockModel {
	/** Mutable call log is the observable behavior of this test double. */
	readonly systemPrompts: string[][] = [];

	invoke(systemPrompt: readonly string[]): void {
		this.systemPrompts.push([...systemPrompt]);
	}
}

export class MockBashTool {
	/** Mutable execution log proves pre-execution interception and rewrite behavior. */
	readonly executions: BashToolInput[] = [];

	constructor(private readonly effect?: BashEffect) {}

	async execute(input: BashToolInput): Promise<BashToolInput> {
		const executedInput = structuredClone(input);
		this.executions.push(executedInput);
		await this.effect?.(executedInput);
		return executedInput;
	}
}

export type RuntimeHarness = {
	readonly runner: ExtensionRunner;
	readonly sessionManager: SessionManager;
	readonly model: MockModel;
	readonly bashTool: MockBashTool;
	readonly sentMessages: string[];
	executeBash(input: BashToolInput, toolCallId?: string): Promise<BashExecutionOutcome>;
	invokeModel(prompt: string, systemPrompt?: string[]): Promise<readonly string[]>;
	close(): Promise<void>;
};

type RuntimeHarnessOptions = {
	readonly bashEffect?: BashEffect;
	readonly cwd?: string;
};

function isRecord(value: unknown): value is Readonly<Record<string, unknown>> {
	return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseStringMap(value: unknown): Record<string, string> | undefined {
	if (!isRecord(value)) return undefined;
	const parsed: Record<string, string> = {};
	for (const [key, entry] of Object.entries(value)) {
		if (typeof entry !== "string") return undefined;
		parsed[key] = entry;
	}
	return parsed;
}

function parseBashInput(value: unknown): BashToolInput | undefined {
	if (!isRecord(value) || typeof value.command !== "string") return undefined;
	const keys = Object.keys(value);
	const allowedKeys = new Set(["command", "env", "timeout", "cwd", "async", "pty"]);
	if (!keys.every(key => allowedKeys.has(key))) return undefined;
	const env = value.env === undefined ? undefined : parseStringMap(value.env);
	if (value.env !== undefined && env === undefined) return undefined;
	if (value.timeout !== undefined && typeof value.timeout !== "number") return undefined;
	if (value.cwd !== undefined && typeof value.cwd !== "string") return undefined;
	if (value.async !== undefined && typeof value.async !== "boolean") return undefined;
	if (value.pty !== undefined && typeof value.pty !== "boolean") return undefined;
	return {
		command: value.command,
		...(env === undefined ? {} : { env }),
		...(typeof value.timeout === "number" ? { timeout: value.timeout } : {}),
		...(typeof value.cwd === "string" ? { cwd: value.cwd } : {}),
		...(typeof value.async === "boolean" ? { async: value.async } : {}),
		...(typeof value.pty === "boolean" ? { pty: value.pty } : {}),
	};
}

async function loadStagedFactory(): Promise<ExtensionFactory> {
	const stagedModule = await import("../staged/omp_extension.ts");
	return stagedModule.default;
}

export async function createRuntimeHarness(options: RuntimeHarnessOptions = {}): Promise<RuntimeHarness> {
	const root = await mkdtemp(path.join(tmpdir(), "slopgate-omp-runner-"));
	const cwd = options.cwd ?? ".";
	const authStorage = await AuthStorage.create(path.join(root, "auth.db"));
	const modelRegistry = new ModelRegistry(authStorage, path.join(root, "models.yml"), {
		cacheDbPath: path.join(root, "models-cache.db"),
		ignoreLocalModelConfig: true,
	});
	const sessionManager = SessionManager.inMemory(cwd);
	const runtime = new ExtensionRuntime();
	const factory = await loadStagedFactory();
	const extension = await loadExtensionFromFactory(factory, cwd, new EventBus(), runtime, "slopgate-staged");
	const runner = new ExtensionRunner([extension], runtime, cwd, sessionManager, modelRegistry);
	const sentMessages: string[] = [];
	const model = new MockModel();
	const bashTool = new MockBashTool(options.bashEffect);
	const actions = {
		sendMessage: message => {
			if (typeof message === "string") sentMessages.push(message);
			if (isRecord(message) && typeof message.content === "string") sentMessages.push(message.content);
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

	return {
		runner,
		sessionManager,
		model,
		bashTool,
		sentMessages,
		async executeBash(input, toolCallId = "tool-call-fixed") {
			const result = await runner.emitToolCall({ type: "tool_call", toolCallId, toolName: "bash", input });
			if (result?.block) return { kind: "blocked", reason: result.reason ?? "Blocked by extension" };
			const rewritten = parseBashInput(result?.input) ?? input;
			return { kind: "executed", input: await bashTool.execute(rewritten) };
		},
		async invokeModel(prompt, systemPrompt = []) {
			const result = await runner.emitBeforeAgentStart(prompt, undefined, systemPrompt);
			const effectivePrompt = result?.systemPrompt ?? systemPrompt;
			model.invoke(effectivePrompt);
			return effectivePrompt;
		},
		async close() {
			await sessionManager.close();
			authStorage.close();
			await rm(root, { force: true, recursive: true });
		},
	};
}
