import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, test } from "bun:test";
import { rm } from "node:fs/promises";

import { createRuntimeHarness, type RuntimeHarness } from "./runtime-harness.ts";
import {
	clearRuntimeEnvironment,
	collectContinuationFlags,
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

const FULL_CONTINUATION_BUDGET = [true, true, true, true, true, true, true, true] as const;

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

		test("injects cached session context locally without forwarding before_agent_start", async () => {
			// Given
			const activeHarness = requireHarness(harness);
			const root = await createTemporaryRoot("slopgate-omp-before-agent-");
			temporaryPaths.push(root);
			configureFakeResponse({ context: "SESSION_CONTEXT_TOKEN" });
			await activeHarness.runner.emit({ type: "session_start" });
			const recordPath = await createRecordPath(root, "unexpected-forward.json");

			// When
			const systemPrompt = await activeHarness.invokeModel("next", ["BASE_SYSTEM_TOKEN"]);

			// Then
			expect(systemPrompt[1]).toContain("SESSION_CONTEXT_TOKEN");
			expect(await Bun.file(recordPath).exists()).toBe(false);
		}, 30000);

		test("caches turn_end guidance for the next model invocation", async () => {
			// Given
			const activeHarness = requireHarness(harness);
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

		test("treats agent_end findings as telemetry without blocking or visible enforcement", async () => {
			const activeHarness = requireHarness(harness);
			const root = await createTemporaryRoot("slopgate-omp-agent-end-");
			temporaryPaths.push(root);
			const before = activeHarness.sentMessages.length;
			configureFakeResponse({ block: true, reason: "AGENT_END_BLOCK_TOKEN" });
			const recordPath = await createRecordPath(root, "agent-end.json");
			const result = await activeHarness.runner.emit({ type: "agent_end", messages: [], willContinue: false });
			const payload = await readRecordedPayload(recordPath);
			expect({ result, displayed: activeHarness.sentMessages.length - before, event: payload.hook_event_name }).toEqual({
				result: undefined,
				displayed: 0,
				event: "agent_end",
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

		test("cap exhaustion settles the ninth stop and restores eight fresh continuations", async () => {
			// Given
			const activeHarness = requireHarness(harness);
			configureFakeResponse({ continue: true, additionalContext: "CONTINUE_TOKEN" });
			await requestContinuations(activeHarness, 8);
			const before = activeHarness.sentMessages.length;

			// When
			const ninth = await emitStop(activeHarness, { turnId: 9 });
			const fresh = await collectContinuationFlags(activeHarness, 8, 20);

			// Then
			expect({ ninth, displayed: activeHarness.sentMessages.length - before, fresh }).toEqual({
				ninth: undefined,
				displayed: 1,
				fresh: FULL_CONTINUATION_BUDGET,
			});
		}, 30000);

		test("input reset restores eight fresh continuations", async () => {
			// Given
			const activeHarness = requireHarness(harness);
			configureFakeResponse({ continue: true, additionalContext: "CONTINUE_TOKEN" });
			await requestContinuations(activeHarness, 8);

			// When
			await activeHarness.runner.emitInput("reset", undefined, "extension");
			const fresh = await collectContinuationFlags(activeHarness, 8, 20);

			// Then
			expect(fresh).toEqual(FULL_CONTINUATION_BUDGET);
		}, 30000);

		test("stop_hook_active settle restores eight fresh continuations", async () => {
			// Given
			const activeHarness = requireHarness(harness);
			configureFakeResponse({ continue: true, additionalContext: "CONTINUE_TOKEN" });
			await requestContinuations(activeHarness, 8);

			// When
			const active = await emitStop(activeHarness, { active: true, turnId: 9 });
			const fresh = await collectContinuationFlags(activeHarness, 8, 20);

			// Then
			expect({ active, fresh }).toEqual({ active: undefined, fresh: FULL_CONTINUATION_BUDGET });
		}, 30000);

		test.each([
			["clean stop", async (activeHarness: RuntimeHarness) => {
				configureFakeResponse({});
				await emitStop(activeHarness);
			}],
			["advisory settle", async (activeHarness: RuntimeHarness) => {
				configureFakeResponse({ additionalContext: "GUIDANCE_RESET_TOKEN" });
				await emitStop(activeHarness);
			}],
			["session start", async (activeHarness: RuntimeHarness) => {
				configureFakeResponse({});
				await activeHarness.runner.emit({ type: "session_start" });
			}],
		] as const)("restores eight fresh continuations after %s", async (_name, reset) => {
			// Given
			const activeHarness = requireHarness(harness);
			configureFakeResponse({ continue: true, additionalContext: "CONTINUE_TOKEN" });
			await requestContinuations(activeHarness, 8);

			// When
			await reset(activeHarness);
			configureFakeResponse({ continue: true, additionalContext: "CONTINUE_TOKEN" });
			const fresh = await collectContinuationFlags(activeHarness, 8, 20);

			// Then
			expect(fresh).toEqual(FULL_CONTINUATION_BUDGET);
		}, 30000);

		test("session B start prunes session A stale cap and restores eight continuations on revisit", async () => {
			// Given
			const sessionA = requireHarness(harness);
			delete process.env.SLOPGATE_SESSION_ID;
			await sessionA.runner.emit({ type: "session_start" });
			const sessionAId = sessionA.sessionManager.getSessionId();
			configureFakeResponse({ continue: true, additionalContext: "CONTINUE_TOKEN" });
			await requestContinuations(sessionA, 8);

			// When
			const sessionB = await createRuntimeHarness();
			const sessionBId = sessionB.sessionManager.getSessionId();
			configureFakeResponse({});
			await sessionB.runner.emit({ type: "session_start" });
			await sessionB.close();
			configureFakeResponse({ continue: true, additionalContext: "CONTINUE_TOKEN" });
			const fresh = await collectContinuationFlags(sessionA, 8, 20);

			// Then
			expect({ distinctSessions: sessionAId !== sessionBId, fresh }).toEqual({
				distinctSessions: true,
				fresh: FULL_CONTINUATION_BUDGET,
			});
		}, 30000);
	});
}
