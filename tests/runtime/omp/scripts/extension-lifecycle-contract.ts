import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, test } from "bun:test";
import { rm } from "node:fs/promises";

import { createRuntimeHarness, type RuntimeHarness } from "./runtime-harness.ts";
import {
	clearRuntimeEnvironment,
	configureFakeResponse,
	configureRuntimeEnvironment,
	createRecordPath,
	createTemporaryRoot,
	emitStop,
	FIXED_SESSION_ID,
	mixedMessage,
	nonTextMessage,
	readRecordedPayload,
	requestContinuations,
	textMessage,
} from "./runtime-test-support.ts";

type ResetKind = "clean-stop" | "guidance" | "session-start";

class LifecycleHarnessStateError extends Error {
	constructor() {
		super("Extension lifecycle harness is unavailable");
		this.name = "LifecycleHarnessStateError";
	}
}

function requireHarness(harness: RuntimeHarness | undefined): RuntimeHarness {
	if (harness === undefined) throw new LifecycleHarnessStateError();
	return harness;
}

async function applyReset(harness: RuntimeHarness, kind: ResetKind): Promise<void> {
	switch (kind) {
		case "clean-stop":
			configureFakeResponse({});
			await emitStop(harness);
			return;
		case "guidance":
			configureFakeResponse({ additionalContext: "GUIDANCE_RESET_TOKEN" });
			await emitStop(harness);
			return;
		case "session-start":
			configureFakeResponse({});
			await harness.runner.emit({ type: "session_start" });
			return;
	}
}

export function registerExtensionLifecycleContractTests(): void {
	describe("staged OMP lifecycle contract", () => {
		const temporaryPaths: string[] = [];
		let harness: RuntimeHarness | undefined;

		beforeAll(async () => {
			configureRuntimeEnvironment();
			harness = await createRuntimeHarness();
		});

		beforeEach(async () => {
			configureFakeResponse({});
			process.env.SLOPGATE_SESSION_ID = FIXED_SESSION_ID;
			await requireHarness(harness).runner.emit({ type: "session_start" });
		});

		afterEach(async () => {
			await Promise.all(temporaryPaths.splice(0).map(root => rm(root, { recursive: true, force: true })));
		});

		afterAll(async () => {
			await harness?.close();
			clearRuntimeEnvironment();
		});

		test.each([
			["text", { text: "TEXT_REPLACEMENT" }, { text: "TEXT_REPLACEMENT" }],
			["updated text", { updated_input: { text: "UPDATED_TEXT" } }, { text: "UPDATED_TEXT" }],
			["updated prompt", { updated_input: { prompt: "UPDATED_PROMPT" } }, { text: "UPDATED_PROMPT" }],
		] as const)("returns the pinned input transform for %s", async (_name, response, expected) => {
			// Given
			configureFakeResponse(response);

			// When
			const result = await requireHarness(harness).runner.emitInput("original", undefined, "extension");

			// Then
			expect(result).toEqual(expected);
		}, 30000);

		test("short-circuits blocked input and emits visible activity", async () => {
			// Given
			const activeHarness = requireHarness(harness);
			const before = activeHarness.sentMessages.length;
			configureFakeResponse({ block: true, reason: "INPUT_BLOCK_TOKEN" });

			// When
			const result = await activeHarness.runner.emitInput("blocked", undefined, "extension");

			// Then
			expect(result).toEqual({ handled: true });
			expect(activeHarness.sentMessages.slice(before)).toEqual(["INPUT_BLOCK_TOKEN"]);
		}, 30000);

		test("caches session and turn guidance for the next model invocation", async () => {
			// Given
			const activeHarness = requireHarness(harness);
			configureFakeResponse({ context: "SESSION_CONTEXT_TOKEN" });
			await activeHarness.runner.emit({ type: "session_start" });
			configureFakeResponse({ additionalContext: "TURN_GUIDANCE_TOKEN" });
			await activeHarness.runner.emit({
				type: "turn_end",
				turnIndex: 1,
				message: textMessage("turn complete"),
				toolResults: [],
			});

			// When
			const systemPrompt = await activeHarness.invokeModel("next", ["BASE_SYSTEM_TOKEN"]);

			// Then
			expect(systemPrompt).toHaveLength(2);
			expect(systemPrompt[1]).toContain("SESSION_CONTEXT_TOKEN");
			expect(systemPrompt[1]).toContain("TURN_GUIDANCE_TOKEN");
			expect(activeHarness.model.systemPrompts.at(-1)).toEqual([...systemPrompt]);
		}, 30000);

		test("merges the configured tool-result details patch", async () => {
			// Given
			configureFakeResponse({ tool_result_patch: { details: { slopgate: "PATCH_TOKEN" }, isError: true } });

			// When
			const result = await requireHarness(harness).runner.emitToolResult({
				type: "tool_result",
				toolCallId: "tool-result-fixed",
				toolName: "custom",
				input: {},
				content: [{ type: "text", text: "result" }],
				details: { existing: true },
				isError: false,
			});

			// Then
			expect(result).toEqual({
				content: [{ type: "text", text: "result" }],
				details: { existing: true, slopgate: "PATCH_TOKEN" },
				isError: false,
			});
		}, 30000);

		test.each([
			["string", textMessage("plain stop"), "plain stop"],
			["mixed array", mixedMessage(), "first\nsecond"],
			["absent", undefined, ""],
			["non-text", nonTextMessage(), ""],
		] as const)("binds %s session-stop content to the exact stop_response", async (_name, message, expected) => {
			// Given
			const root = await createTemporaryRoot("slopgate-omp-stop-binding-");
			temporaryPaths.push(root);
			const recordPath = await createRecordPath(root, "stop.json");

			// When
			await emitStop(requireHarness(harness), { lastMessage: message });
			const payload = await readRecordedPayload(recordPath);

			// Then
			expect(payload.stop_response).toBe(expected);
		}, 30000);

		test("caps the ninth continuation and emits one visible cap event", async () => {
			// Given
			const activeHarness = requireHarness(harness);
			configureFakeResponse({ continue: true, additionalContext: "CONTINUE_TOKEN" });
			await requestContinuations(activeHarness, 8);
			const before = activeHarness.sentMessages.length;

			// When
			const ninth = await emitStop(activeHarness, { turnId: 9 });

			// Then
			expect(ninth).toBeUndefined();
			expect(activeHarness.sentMessages).toHaveLength(before + 1);
		}, 30000);

		test("resets the continuation counter on input", async () => {
			// Given
			const activeHarness = requireHarness(harness);
			configureFakeResponse({ continue: true, additionalContext: "CONTINUE_TOKEN" });
			await requestContinuations(activeHarness, 8);

			// When
			await activeHarness.runner.emitInput("reset", undefined, "extension");
			const next = await emitStop(activeHarness, { turnId: 9 });

			// Then
			expect(next?.continue).toBe(true);
		}, 30000);

		test("resets the continuation counter on an active stop pass", async () => {
			// Given
			const activeHarness = requireHarness(harness);
			configureFakeResponse({ continue: true, additionalContext: "CONTINUE_TOKEN" });
			await requestContinuations(activeHarness, 8);

			// When
			const active = await emitStop(activeHarness, { active: true, turnId: 9 });
			const next = await emitStop(activeHarness, { turnId: 10 });

			// Then
			expect(active).toBeUndefined();
			expect(next?.continue).toBe(true);
		}, 30000);

		test.each(["clean-stop", "guidance", "session-start"] as const)("resets after %s", async kind => {
			// Given
			const activeHarness = requireHarness(harness);
			configureFakeResponse({ continue: true, additionalContext: "CONTINUE_TOKEN" });
			await requestContinuations(activeHarness, 8);

			// When
			await applyReset(activeHarness, kind);
			configureFakeResponse({ continue: true, additionalContext: "CONTINUE_TOKEN" });
			const next = await emitStop(activeHarness, { turnId: 10 });

			// Then
			expect(next?.continue).toBe(true);
		}, 30000);

		test("prunes only the active session counter during an A-B-A revisit", async () => {
			// Given
			const activeHarness = requireHarness(harness);
			configureFakeResponse({ continue: true, additionalContext: "CONTINUE_TOKEN" });
			process.env.SLOPGATE_SESSION_ID = "session-A";
			await requestContinuations(activeHarness, 8);

			// When
			process.env.SLOPGATE_SESSION_ID = "session-B";
			await emitStop(activeHarness, { active: true });
			process.env.SLOPGATE_SESSION_ID = "session-A";
			const revisit = await emitStop(activeHarness, { turnId: 9 });

			// Then
			expect(revisit).toBeUndefined();
		}, 30000);
	});
}
