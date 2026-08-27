import { mkdtemp, mkdir } from "node:fs/promises";
import { tmpdir } from "node:os";
import * as path from "node:path";

import type { AgentMessage } from "@oh-my-pi/pi-agent-core";
import type { BashToolInput } from "@oh-my-pi/pi-coding-agent/tools/bash";

import type { RuntimeHarness } from "./runtime-harness.ts";

export const WORKSPACE_ROOT = path.resolve(import.meta.dir, "..");
export const FAKE_ENFORCER = path.join(WORKSPACE_ROOT, "fake-enforcer/slopgate");
export const FIXED_SESSION_ID = "omp-test-session";

type StopOptions = {
	readonly active?: boolean;
	readonly lastMessage?: AgentMessage;
	readonly sessionId?: string;
	readonly turnId?: number;
};

class ContractFixtureError extends Error {
	constructor(message: string) {
		super(message);
		this.name = "ContractFixtureError";
	}
}

function isRecord(value: unknown): value is Readonly<Record<string, unknown>> {
	return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function configureFakeResponse(response: Readonly<Record<string, unknown>>): void {
	process.env.SLOPGATE_FAKE_RESPONSE = JSON.stringify(response);
	delete process.env.SLOPGATE_FAKE_STDOUT;
	delete process.env.SLOPGATE_FAKE_EXIT_CODE;
	delete process.env.SLOPGATE_FAKE_RECORD_PATH;
}

export function configureFakeFailure(stdout: string, exitCode = 0): void {
	process.env.SLOPGATE_FAKE_STDOUT = stdout;
	process.env.SLOPGATE_FAKE_EXIT_CODE = String(exitCode);
	delete process.env.SLOPGATE_FAKE_RESPONSE;
	delete process.env.SLOPGATE_FAKE_RECORD_PATH;
}

export function configureRuntimeEnvironment(): void {
	process.env.SLOPGATE_BIN = FAKE_ENFORCER;
	process.env.SLOPGATE_SESSION_ID = FIXED_SESSION_ID;
}

export function clearRuntimeEnvironment(): void {
	for (const key of [
		"SLOPGATE_BIN",
		"SLOPGATE_SESSION_ID",
		"SLOPGATE_OMP_INPUT_REWRITE",
		"SLOPGATE_FAKE_RESPONSE",
		"SLOPGATE_FAKE_STDOUT",
		"SLOPGATE_FAKE_EXIT_CODE",
		"SLOPGATE_FAKE_RECORD_PATH",
	]) {
		delete process.env[key];
	}
}

export async function createTemporaryRoot(prefix: string): Promise<string> {
	return await mkdtemp(path.join(tmpdir(), prefix));
}

export async function createRecordPath(root: string, name: string): Promise<string> {
	await mkdir(root, { recursive: true });
	const recordPath = path.join(root, name);
	process.env.SLOPGATE_FAKE_RECORD_PATH = recordPath;
	return recordPath;
}

export async function readRecordedPayload(recordPath: string): Promise<Readonly<Record<string, unknown>>> {
	const parsed: unknown = JSON.parse(await Bun.file(recordPath).text());
	if (!isRecord(parsed)) throw new ContractFixtureError(`Recorded payload is not an object: ${recordPath}`);
	return parsed;
}

export function textMessage(content: string): AgentMessage {
	return { role: "user", content, timestamp: 0 };
}

export function assistantTextMessage(content: string): AgentMessage {
	return {
		role: "assistant",
		content: [{ type: "text", text: content }],
		api: "anthropic-messages",
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
	};
}

export function mixedMessage(): AgentMessage {
	return {
		role: "user",
		content: [
			{ type: "text", text: "first" },
			{ type: "image", data: "AA==", mimeType: "image/png" },
			{ type: "text", text: "second" },
		],
		timestamp: 0,
	};
}

export function nonTextMessage(): AgentMessage {
	return {
		role: "user",
		content: [{ type: "image", data: "AA==", mimeType: "image/png" }],
		timestamp: 0,
	};
}

export async function emitStop(harness: RuntimeHarness, options: StopOptions = {}) {
	return await harness.runner.emitSessionStop({
		messages: [],
		session_id: options.sessionId ?? harness.sessionManager.getSessionId(),
		signal: new AbortController().signal,
		stop_hook_active: options.active ?? false,
		turn_id: options.turnId ?? 1,
		...(options.lastMessage === undefined ? {} : { last_assistant_message: options.lastMessage }),
	});
}

function valueForField(field: string): unknown {
	switch (field) {
		case "command":
			return "printf contract";
		case "cwd":
			return ".";
		case "env":
			return { CONTRACT: "1" };
		case "timeout":
			return 30;
		case "async":
		case "pty":
			return false;
		default:
			throw new ContractFixtureError(`Unexpected bash field: ${field}`);
	}
}

function parseBashInput(value: unknown): BashToolInput {
	if (!isRecord(value) || typeof value.command !== "string") {
		throw new ContractFixtureError("Generated bash fixture is invalid");
	}
	return {
		command: value.command,
		...(isRecord(value.env) ? { env: { CONTRACT: "1" } } : {}),
		...(typeof value.timeout === "number" ? { timeout: value.timeout } : {}),
		...(typeof value.cwd === "string" ? { cwd: value.cwd } : {}),
		...(typeof value.async === "boolean" ? { async: value.async } : {}),
		...(typeof value.pty === "boolean" ? { pty: value.pty } : {}),
	};
}

export async function loadBashVariants(): Promise<readonly BashToolInput[]> {
	const snapshot: unknown = JSON.parse(await Bun.file(path.join(WORKSPACE_ROOT, "contract-snapshot.json")).text());
	if (!isRecord(snapshot) || !isRecord(snapshot.bash_input) || !Array.isArray(snapshot.bash_input.variants)) {
		throw new ContractFixtureError("Snapshot bash variants are missing");
	}
	return snapshot.bash_input.variants.map(variant => {
		if (!isRecord(variant)) throw new ContractFixtureError("Snapshot bash variant is not an object");
		return parseBashInput(Object.fromEntries(Object.keys(variant).map(field => [field, valueForField(field)])));
	});
}

export async function requestContinuations(harness: RuntimeHarness, count: number): Promise<void> {
	for (let index = 0; index < count; index += 1) {
		const result = await emitStop(harness, { turnId: index + 1 });
		if (result?.continue !== true) throw new ContractFixtureError(`Continuation ${index + 1} was not requested`);
	}
}
