import { mkdir, rm } from "node:fs/promises";
import * as path from "node:path";

import { createRuntimeHarness, type RuntimeHarness } from "./runtime-harness.ts";
import {
	assistantTextMessage,
	configureFakeResponse,
	emitStop,
	FAKE_ENFORCER,
	FIXED_SESSION_ID,
} from "./runtime-test-support.ts";

export const CAPTURE_FILES = [
	"before-agent-start.json",
	"input.json",
	"session-start.json",
	"session-stop-advisory.json",
	"session-stop-blocking.json",
	"tool-call-bash.json",
	"tool-call-write.json",
	"tool-result-error.json",
	"tool-result-success.json",
	"turn-end.json",
	"user-bash.json",
	"user-python.json",
] as const;

const CAPTURE_ENVIRONMENT_KEYS = [
	"SLOPGATE_BIN",
	"SLOPGATE_SESSION_ID",
	"SLOPGATE_OMP_INPUT_REWRITE",
	"SLOPGATE_FAKE_REAL_BIN",
	"SLOPGATE_FAKE_RECORD_PATH",
	"SLOPGATE_FAKE_RESPONSE",
	"SLOPGATE_FAKE_STDOUT",
	"SLOPGATE_FAKE_EXIT_CODE",
] as const;

type CaptureFile = (typeof CAPTURE_FILES)[number];
type CaptureAction = () => Promise<unknown>;

class EnvelopeCaptureError extends Error {
	constructor(detail: string) {
		super(`OMP envelope capture failed: ${detail}`);
		this.name = "EnvelopeCaptureError";
	}
}

function snapshotEnvironment(): ReadonlyMap<string, string | undefined> {
	return new Map(CAPTURE_ENVIRONMENT_KEYS.map(key => [key, process.env[key]]));
}

function restoreEnvironment(snapshot: ReadonlyMap<string, string | undefined>): void {
	for (const key of CAPTURE_ENVIRONMENT_KEYS) {
		const value = snapshot.get(key);
		if (value === undefined) delete process.env[key];
		else process.env[key] = value;
	}
}

function configureCaptureEnvironment(): void {
	process.env.SLOPGATE_BIN = FAKE_ENFORCER;
	process.env.SLOPGATE_SESSION_ID = FIXED_SESSION_ID;
	delete process.env.SLOPGATE_OMP_INPUT_REWRITE;
	delete process.env.SLOPGATE_FAKE_REAL_BIN;
	delete process.env.SLOPGATE_FAKE_STDOUT;
	delete process.env.SLOPGATE_FAKE_EXIT_CODE;
}

async function captureWithHarness(outputDir: string, harness: RuntimeHarness): Promise<void> {
	const record = async (
		filename: CaptureFile,
		response: Readonly<Record<string, unknown>>,
		action: CaptureAction,
	): Promise<void> => {
		configureFakeResponse(response);
		const target = path.join(outputDir, filename);
		process.env.SLOPGATE_FAKE_RECORD_PATH = target;
		await action();
		if (!(await Bun.file(target).exists())) throw new EnvelopeCaptureError(`missing ${filename}`);
	};

	await record("session-start.json", {}, async () => await harness.runner.emit({ type: "session_start" }));
	await record("tool-call-bash.json", {}, async () =>
		await harness.runner.emitToolCall({
			type: "tool_call",
			toolCallId: "tool-call-bash-fixed",
			toolName: "bash",
			input: { command: "printf capture", cwd: "." },
		}),
	);
	await record("tool-call-write.json", {}, async () =>
		await harness.runner.emitToolCall({
			type: "tool_call",
			toolCallId: "tool-call-write-fixed",
			toolName: "write",
			input: { path: "capture.txt", content: "captured" },
		}),
	);
	await record("tool-result-success.json", {}, async () =>
		await harness.runner.emitToolResult({
			type: "tool_result",
			toolCallId: "tool-result-success-fixed",
			toolName: "bash",
			input: { command: "printf capture" },
			content: [{ type: "text", text: "capture ok" }],
			details: { exitCode: 0 },
			isError: false,
		}),
	);
	await record("tool-result-error.json", {}, async () =>
		await harness.runner.emitToolResult({
			type: "tool_result",
			toolCallId: "tool-result-error-fixed",
			toolName: "bash",
			input: { command: "false" },
			content: [{ type: "text", text: "capture failed" }],
			details: { exitCode: 1 },
			isError: true,
		}),
	);
	await record("session-stop-blocking.json", { continue: true, additionalContext: "capture continuation" }, async () =>
		await emitStop(harness, {
			lastMessage: assistantTextMessage("blocking stop response"),
			sessionId: FIXED_SESSION_ID,
			turnId: 2,
		}),
	);
	await record("session-stop-advisory.json", { context: "capture advisory" }, async () =>
		await emitStop(harness, {
			lastMessage: assistantTextMessage("advisory stop response"),
			sessionId: FIXED_SESSION_ID,
			turnId: 3,
		}),
	);
	await record("input.json", {}, async () => await harness.runner.emitInput("capture input", undefined, "extension"));
	await record("before-agent-start.json", { context: "capture session context" }, async () => {
		await harness.runner.emit({ type: "session_start" });
		const prompt = await harness.invokeModel("capture turn", ["capture base"]);
		if (!prompt.some(item => item.includes("capture session context"))) {
			throw new EnvelopeCaptureError("before_agent_start did not inject cached context");
		}
	});
	await record("turn-end.json", { additionalContext: "capture turn context" }, async () =>
		await harness.runner.emit({
			type: "turn_end",
			turnIndex: 4,
			message: assistantTextMessage("turn complete"),
			toolResults: [],
		}),
	);
	await record("user-bash.json", {}, async () =>
		await harness.runner.emitUserBash({
			type: "user_bash",
			command: "printf user capture",
			excludeFromContext: false,
			cwd: ".",
		}),
	);
	await record("user-python.json", {}, async () =>
		await harness.runner.emitUserPython({
			type: "user_python",
			code: 'print("user capture")',
			excludeFromContext: false,
			cwd: ".",
		}),
	);
}

export async function captureEnvelopes(outputDir: string): Promise<void> {
	const environment = snapshotEnvironment();
	let harness: RuntimeHarness | undefined;
	try {
		configureCaptureEnvironment();
		await rm(outputDir, { recursive: true, force: true });
		await mkdir(outputDir, { recursive: true });
		harness = await createRuntimeHarness();
		await captureWithHarness(outputDir, harness);
	} finally {
		try {
			await harness?.close();
		} finally {
			restoreEnvironment(environment);
		}
	}
}

export async function assertCaptureDirectoriesEqual(left: string, right: string): Promise<void> {
	for (const filename of CAPTURE_FILES) {
		const [leftBytes, rightBytes] = await Promise.all([
			Bun.file(path.join(left, filename)).arrayBuffer(),
			Bun.file(path.join(right, filename)).arrayBuffer(),
		]);
		if (!Buffer.from(leftBytes).equals(Buffer.from(rightBytes))) {
			throw new EnvelopeCaptureError(`byte mismatch for ${filename}`);
		}
	}
}
