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

		beforeAll(() => {
			configureRuntimeEnvironment();
		});

		// Session state is per identity and startup runs once, so every test owns a fresh session.
		beforeEach(async () => {
			configureFakeResponse({});
			process.env.SLOPGATE_SESSION_ID = FIXED_SESSION_ID;
			harness = await createRuntimeHarness({ withUI: true });
		});

		afterEach(async () => {
			await harness?.close();
			harness = undefined;
			await Promise.all(temporaryPaths.splice(0).map(root => rm(root, { recursive: true, force: true })));
		});

		afterAll(() => {
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

		test("short-circuits blocked input with a notification and no custom message", async () => {
			// Given
			const activeHarness = requireHarness(harness);
			configureFakeResponse({ block: true, reason: "INPUT_BLOCK_TOKEN" });

			// When
			const result = await activeHarness.runner.emitInput("blocked", undefined, "extension");

			// Then
			expect(result).toEqual({ handled: true });
			expect(activeHarness.notifications).toEqual(["INPUT_BLOCK_TOKEN"]);
			expect(activeHarness.sendMessageCalls).toBe(0);
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
			expect(activeHarness.sendMessageCalls).toBe(0);
		}, 30000);

		test("caches turn_end guidance for the next model invocation", async () => {
			// Given
			const activeHarness = requireHarness(harness);
			configureFakeResponse({ context: "TURN_GUIDANCE_TOKEN" });
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

		test.each([
			["explicit true", { isError: true }, false, true],
			["explicit false", { isError: false }, true, false],
			["absent keeps native false", {}, false, false],
			["absent keeps native true", {}, true, true],
		] as const)("merges findings, content, and details into the native result with %s isError", async (_name, patchFlags, nativeIsError, expectedIsError) => {
			// Given
			const original = [
				{ type: "text", text: "result" },
				{ type: "image", data: "AA==", mimeType: "image/png" },
			] as const;
			configureFakeResponse({
				context: "FINDING_TOKEN",
				tool_result_patch: { details: { slopgate: "PATCH_TOKEN" }, ...patchFlags },
			});

			// When
			const result = await requireHarness(harness).runner.emitToolResult({
				type: "tool_result",
				toolCallId: "tool-result-fixed",
				toolName: "custom",
				input: {},
				content: [...original],
				details: { existing: true },
				isError: nativeIsError,
			});

			// Then
			expect(result).toEqual({
				content: [...original, { type: "text", text: "Slopgate findings:\nFINDING_TOKEN" }],
				details: { existing: true, slopgate: "PATCH_TOKEN" },
				isError: expectedIsError,
			});
		}, 30000);

		test("leaves the native tool result untouched when the enforcer reports nothing", async () => {
			// Given
			configureFakeResponse({});

			// When
			const result = await requireHarness(harness).runner.emitToolResult({
				type: "tool_result",
				toolCallId: "tool-result-quiet",
				toolName: "custom",
				input: {},
				content: [{ type: "text", text: "result" }],
				details: { existing: true },
				isError: false,
			});

			// Then
			expect(result).toBeUndefined();
		}, 30000);

		test("treats agent_end findings as telemetry that never vetoes and is delivered on the next request", async () => {
			const activeHarness = requireHarness(harness);
			const root = await createTemporaryRoot("slopgate-omp-agent-end-");
			temporaryPaths.push(root);
			configureFakeResponse({ block: true, reason: "AGENT_END_BLOCK_TOKEN" });
			const recordPath = await createRecordPath(root, "agent-end.json");
			const result = await activeHarness.runner.emit({ type: "agent_end", messages: [], willContinue: false });
			const payload = await readRecordedPayload(recordPath);
			const systemPrompt = await activeHarness.invokeModel("next", ["BASE_SYSTEM_TOKEN"]);
			expect({
				result,
				displayed: activeHarness.sendMessageCalls,
				event: payload.hook_event_name,
				carried: systemPrompt[1]?.includes("AGENT_END_BLOCK_TOKEN"),
			}).toEqual({
				result: undefined,
				displayed: 0,
				event: "agent_end",
				carried: true,
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
			const before = activeHarness.notifications.length;

			// When
			const ninth = await emitStop(activeHarness, { turnId: 9 });
			const fresh = await collectContinuationFlags(activeHarness, 8, 20);

			// Then
			expect({ ninth, displayed: activeHarness.notifications.slice(before), fresh }).toEqual({
				ninth: undefined,
				displayed: ["slopgate: continuation cap reached (8); fix remaining findings manually."],
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
			["session switch", async (activeHarness: RuntimeHarness) => {
				configureFakeResponse({});
				await activeHarness.runner.emit({ type: "session_switch", reason: "new", previousSessionFile: undefined });
			}],
			["session branch", async (activeHarness: RuntimeHarness) => {
				configureFakeResponse({});
				await activeHarness.runner.emit({ type: "session_branch", previousSessionFile: undefined });
			}],
			["session tree", async (activeHarness: RuntimeHarness) => {
				configureFakeResponse({});
				await activeHarness.runner.emit({ type: "session_tree", newLeafId: null, oldLeafId: null });
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
	});
}
