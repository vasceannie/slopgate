import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, test } from "bun:test";

import { createRuntimeHarness, type RuntimeHarness } from "./runtime-harness.ts";
import {
	clearRuntimeEnvironment,
	configureFakeFailure,
	configureFakeResponse,
	configureRuntimeEnvironment,
	emitStop,
	FIXED_SESSION_ID,
	textMessage,
} from "./runtime-test-support.ts";

const PROMPT_HEADER = "Slopgate hook context for this turn:";
const FINDINGS_HEADER = "Slopgate findings:";
const BASE_PROMPT = ["BASE_SYSTEM_TOKEN"];

class DeliveryHarnessStateError extends Error {
	constructor() {
		super("Delivery contract harness is unavailable");
		this.name = "DeliveryHarnessStateError";
	}
}

function requireHarness(harness: RuntimeHarness | undefined): RuntimeHarness {
	if (harness === undefined) throw new DeliveryHarnessStateError();
	return harness;
}

function occurrences(haystack: string, needle: string): number {
	return haystack.split(needle).length - 1;
}

function blockText(systemPrompt: readonly string[]): string {
	return systemPrompt.slice(BASE_PROMPT.length).join("\n");
}

async function emitTurnEnd(harness: RuntimeHarness): Promise<void> {
	await harness.runner.emit({ type: "turn_end", turnIndex: 1, message: textMessage("turn complete"), toolResults: [] });
}

async function readOnlyToolCall(harness: RuntimeHarness, toolCallId: string) {
	return await harness.runner.emitToolCall({
		type: "tool_call",
		toolCallId,
		toolName: "read",
		input: { path: "README.md" },
	});
}

async function emitToolResult(harness: RuntimeHarness, toolCallId: string, isError: boolean) {
	return await harness.runner.emitToolResult({
		type: "tool_result",
		toolCallId,
		toolName: "custom",
		input: {},
		content: [{ type: "text", text: "native output" }],
		details: { native: true },
		isError,
	});
}

export function registerExtensionDeliveryContractTests(): void {
	describe("staged OMP per-request delivery contract", () => {
		let harness: RuntimeHarness | undefined;

		beforeAll(() => {
			configureRuntimeEnvironment();
		});

		beforeEach(async () => {
			configureFakeResponse({});
			process.env.SLOPGATE_SESSION_ID = FIXED_SESSION_ID;
			harness = await createRuntimeHarness();
		});

		afterEach(async () => {
			await harness?.close();
			harness = undefined;
		});

		afterAll(() => {
			clearRuntimeEnvironment();
		});

		test("two prompts each produce exactly one system-prompt block and no custom message", async () => {
			// Given
			const activeHarness = requireHarness(harness);
			configureFakeResponse({ context: "PROMPT_ONE_TOKEN" });
			await activeHarness.runner.emitInput("one", undefined, "extension");

			// When
			const first = await activeHarness.invokeModel("one", BASE_PROMPT);
			configureFakeResponse({});
			await emitTurnEnd(activeHarness);
			configureFakeResponse({ context: "PROMPT_TWO_TOKEN" });
			await activeHarness.runner.emitInput("two", undefined, "extension");
			const second = await activeHarness.invokeModel("two", BASE_PROMPT);

			// Then
			expect({
				firstBlocks: first.length - BASE_PROMPT.length,
				firstHeaders: occurrences(blockText(first), PROMPT_HEADER),
				firstHasOne: blockText(first).includes("PROMPT_ONE_TOKEN"),
				secondBlocks: second.length - BASE_PROMPT.length,
				secondHeaders: occurrences(blockText(second), PROMPT_HEADER),
				secondHasTwo: blockText(second).includes("PROMPT_TWO_TOKEN"),
				secondHasOne: blockText(second).includes("PROMPT_ONE_TOKEN"),
				customMessages: activeHarness.sendMessageCalls,
			}).toEqual({
				firstBlocks: 1,
				firstHeaders: 1,
				firstHasOne: true,
				secondBlocks: 1,
				secondHeaders: 1,
				secondHasTwo: true,
				secondHasOne: false,
				customMessages: 0,
			});
		}, 30000);

		test("preparing twice before turn_end delivers guidance both times and consumes it afterwards", async () => {
			// Given
			const activeHarness = requireHarness(harness);
			configureFakeResponse({ context: "GUIDANCE_TOKEN" });
			await emitTurnEnd(activeHarness);
			configureFakeResponse({});

			// When
			const first = await activeHarness.invokeModel("first", BASE_PROMPT);
			const retried = await activeHarness.invokeModel("retry", BASE_PROMPT);
			await emitTurnEnd(activeHarness);
			const afterTurn = await activeHarness.invokeModel("next", BASE_PROMPT);

			// Then
			expect({
				first: blockText(first).includes("GUIDANCE_TOKEN"),
				retried: blockText(retried).includes("GUIDANCE_TOKEN"),
				consumed: afterTurn,
			}).toEqual({ first: true, retried: true, consumed: BASE_PROMPT });
		}, 30000);

		test("a newer input staged after an older preparation survives that older turn's end", async () => {
			// Given
			const activeHarness = requireHarness(harness);
			configureFakeResponse({ context: "OLD_CONTEXT_TOKEN" });
			await activeHarness.runner.emitInput("old", undefined, "extension");
			await activeHarness.invokeModel("old", BASE_PROMPT);
			configureFakeResponse({ context: "NEW_CONTEXT_TOKEN" });
			await activeHarness.runner.emitInput("new", undefined, "extension");

			// When
			configureFakeResponse({});
			await emitTurnEnd(activeHarness);
			const next = await activeHarness.invokeModel("new", BASE_PROMPT);

			// Then
			expect({
				newer: blockText(next).includes("NEW_CONTEXT_TOKEN"),
				older: blockText(next).includes("OLD_CONTEXT_TOKEN"),
			}).toEqual({ newer: true, older: false });
		}, 30000);

		test("a UI-only command input followed by a real prompt prepares only the real prompt's context", async () => {
			// Given
			const activeHarness = requireHarness(harness);
			configureFakeResponse({ context: "SLASH_COMMAND_TOKEN" });
			await activeHarness.runner.emitInput("/ui-only", undefined, "interactive");
			configureFakeResponse({ context: "REAL_PROMPT_TOKEN" });
			await activeHarness.runner.emitInput("real prompt", undefined, "interactive");

			// When
			const prepared = await activeHarness.invokeModel("real prompt", BASE_PROMPT);

			// Then
			expect({
				real: blockText(prepared).includes("REAL_PROMPT_TOKEN"),
				slash: blockText(prepared).includes("SLASH_COMMAND_TOKEN"),
			}).toEqual({ real: true, slash: false });
		}, 30000);

		test.each([
			["settled", false],
			["stop_hook_active", true],
		] as const)("non-blocking %s session_stop advice is staged for the next prompt without a custom message", async (_name, active) => {
			// Given
			const activeHarness = requireHarness(harness);
			configureFakeResponse({ additionalContext: "STOP_ADVICE_TOKEN" });

			// When
			const stopped = await emitStop(activeHarness, { active });
			configureFakeResponse({});
			const prepared = await activeHarness.invokeModel("next", BASE_PROMPT);
			await emitTurnEnd(activeHarness);
			const consumed = await activeHarness.invokeModel("after", BASE_PROMPT);

			// Then
			expect({
				stopped,
				delivered: blockText(prepared).includes("STOP_ADVICE_TOKEN"),
				consumed,
				customMessages: activeHarness.sendMessageCalls,
			}).toEqual({ stopped: undefined, delivered: true, consumed: BASE_PROMPT, customMessages: 0 });
		}, 30000);

		test("a revive preparation neither prepares nor consumes pending context", async () => {
			// Given
			const activeHarness = requireHarness(harness);
			configureFakeResponse({ context: "PENDING_TOKEN" });
			await activeHarness.runner.emitInput("staged", undefined, "extension");
			configureFakeResponse({});
			const handlers = activeHarness.extension.handlers.get("before_agent_start") ?? [];
			const createContext: unknown = Reflect.get(activeHarness.runner, "createContext");
			if (typeof createContext !== "function") throw new DeliveryHarnessStateError();
			const ctx: unknown = Reflect.apply(createContext, activeHarness.runner, []);

			// When
			const revived = await handlers[0]?.(
				{ type: "before_agent_start", reason: "revive", prompt: "revive", systemPrompt: [...BASE_PROMPT] },
				ctx,
			);
			await emitTurnEnd(activeHarness);
			const real = await activeHarness.invokeModel("real", BASE_PROMPT);

			// Then
			expect({ revived, delivered: blockText(real).includes("PENDING_TOKEN") }).toEqual({
				revived: undefined,
				delivered: true,
			});
		}, 30000);

		test.each([
			["success", false],
			["failure", true],
		] as const)("pre-tool context reaches the native result of a %s even when post-tool evaluation is empty", async (_name, isError) => {
			// Given
			const activeHarness = requireHarness(harness);
			configureFakeResponse({ context: "PRE_TOOL_TOKEN" });
			const preToolResult = await readOnlyToolCall(activeHarness, "pre-tool-call");
			configureFakeFailure("", 0);

			// When
			const merged = await emitToolResult(activeHarness, "pre-tool-call", isError);

			// Then
			expect(preToolResult).toBeUndefined();
			expect(merged).toEqual({
				content: [
					{ type: "text", text: "native output" },
					{ type: "text", text: `${FINDINGS_HEADER}\nPRE_TOOL_TOKEN` },
				],
				details: { native: true },
				isError,
			});
		}, 30000);

		test("a stored pre-tool entry is not reused by a duplicate result", async () => {
			// Given
			const activeHarness = requireHarness(harness);
			configureFakeResponse({ context: "ONCE_ONLY_TOKEN" });
			await readOnlyToolCall(activeHarness, "duplicate-call");
			configureFakeFailure("", 0);
			await emitToolResult(activeHarness, "duplicate-call", false);

			// When
			const duplicate = await emitToolResult(activeHarness, "duplicate-call", false);

			// Then
			expect(duplicate).toBeUndefined();
		}, 30000);

		test("pre-tool and post-tool fragments are deduplicated into one findings block", async () => {
			// Given
			const activeHarness = requireHarness(harness);
			configureFakeResponse({ context: "SHARED_FINDING_TOKEN" });
			await readOnlyToolCall(activeHarness, "dedupe-call");

			// When
			const merged = await emitToolResult(activeHarness, "dedupe-call", false);

			// Then
			expect(merged?.content).toEqual([
				{ type: "text", text: "native output" },
				{ type: "text", text: `${FINDINGS_HEADER}\nSHARED_FINDING_TOKEN` },
			]);
		}, 30000);

		test("a blocked tool call creates no pending context for its result", async () => {
			// Given
			const activeHarness = requireHarness(harness);
			configureFakeResponse({ block: true, reason: "BLOCKED_CALL_TOKEN", context: "BLOCKED_CONTEXT_TOKEN" });
			const blocked = await readOnlyToolCall(activeHarness, "blocked-call");
			configureFakeFailure("", 0);

			// When
			const merged = await emitToolResult(activeHarness, "blocked-call", false);

			// Then
			expect({ blocked, merged }).toEqual({
				blocked: { block: true, reason: "BLOCKED_CALL_TOKEN" },
				merged: undefined,
			});
		}, 30000);
	});
}
