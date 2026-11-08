import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, test } from "bun:test";
import { rm } from "node:fs/promises";
import * as path from "node:path";

import { createRuntimeHarness, type RuntimeHarness } from "./runtime-harness.ts";
import {
	clearRuntimeEnvironment,
	collectContinuationFlags,
	configureFakeResponse,
	configureInvocationLog,
	configureRuntimeEnvironment,
	createTemporaryRoot,
	emitStop,
	FIXED_SESSION_ID,
	readInvocationLog,
	requestContinuations,
	textMessage,
} from "./runtime-test-support.ts";

const BASE_PROMPT = ["BASE_SYSTEM_TOKEN"];
const FULL_CONTINUATION_BUDGET = [true, true, true, true, true, true, true, true] as const;
const STARTUP_EVALUATION = "session_start";

function blockText(systemPrompt: readonly string[]): string {
	return systemPrompt.slice(BASE_PROMPT.length).join("\n");
}

async function emitTurnEnd(harness: RuntimeHarness): Promise<void> {
	await harness.runner.emit({ type: "turn_end", turnIndex: 1, message: textMessage("turn complete"), toolResults: [] });
}

async function startupEvaluations(logPath: string): Promise<number> {
	return (await readInvocationLog(logPath)).filter(line => line === STARTUP_EVALUATION).length;
}

async function stageGuidance(harness: RuntimeHarness, token: string): Promise<void> {
	configureFakeResponse({ context: token });
	await emitTurnEnd(harness);
	configureFakeResponse({});
}

export function registerExtensionSessionContractTests(): void {
	describe("staged OMP session isolation contract", () => {
		const opened: RuntimeHarness[] = [];
		let temporaryRoot: string | undefined;
		let logPath = "";

		const open = async (options: Parameters<typeof createRuntimeHarness>[0] = {}): Promise<RuntimeHarness> => {
			const created = await createRuntimeHarness({ withUI: true, ...options });
			opened.push(created);
			return created;
		};

		beforeAll(() => {
			configureRuntimeEnvironment();
		});

		beforeEach(async () => {
			configureFakeResponse({});
			process.env.SLOPGATE_SESSION_ID = FIXED_SESSION_ID;
			temporaryRoot = await createTemporaryRoot("slopgate-omp-session-");
			logPath = path.join(temporaryRoot, "invocations.log");
			configureInvocationLog(logPath);
		});

		afterEach(async () => {
			await Promise.all(opened.splice(0).map(created => created.close()));
			configureInvocationLog(undefined);
			if (temporaryRoot !== undefined) await rm(temporaryRoot, { recursive: true, force: true });
			temporaryRoot = undefined;
		});

		afterAll(() => {
			clearRuntimeEnvironment();
		});

		test("a repeated startup for one identity launches one evaluation and keeps its context", async () => {
			// Given
			const session = await open();
			configureFakeResponse({ context: "STARTUP_TOKEN" });
			await session.runner.emit({ type: "session_start" });

			// When
			configureFakeResponse({ context: "REPLAYED_TOKEN" });
			await session.runner.emit({ type: "session_start" });
			const prepared = await session.invokeModel("next", BASE_PROMPT);

			// Then
			expect({
				evaluations: await startupEvaluations(logPath),
				original: blockText(prepared).includes("STARTUP_TOKEN"),
				replayed: blockText(prepared).includes("REPLAYED_TOKEN"),
			}).toEqual({ evaluations: 1, original: true, replayed: false });
		}, 30000);

		test("a failed startup keeps its degraded reason for the next request without retrying", async () => {
			// Given
			const session = await open();
			configureFakeResponse({ block: true, reason: "STARTUP_DEGRADED_TOKEN" });

			// When
			await session.runner.emit({ type: "session_start" });
			await session.runner.emit({ type: "session_start" });
			configureFakeResponse({});
			const prepared = await session.invokeModel("next", BASE_PROMPT);

			// Then
			expect({
				evaluations: await startupEvaluations(logPath),
				notified: session.notifications,
				carried: blockText(prepared).includes("STARTUP_DEGRADED_TOKEN"),
			}).toEqual({ evaluations: 1, notified: ["STARTUP_DEGRADED_TOKEN"], carried: true });
		}, 30000);

		test("A to B to A reuses A's startup context but drops A's stale pending guidance", async () => {
			// Given
			const sessionA = await open();
			configureFakeResponse({ context: "CONTEXT_A_TOKEN" });
			await sessionA.runner.emit({ type: "session_start" });
			const sessionB = await open({ extension: sessionA.extension });
			configureFakeResponse({ context: "CONTEXT_B_TOKEN" });
			await sessionB.runner.emit({ type: "session_start" });
			await stageGuidance(sessionA, "STALE_A_TOKEN");

			// When
			configureFakeResponse({});
			await sessionB.runner.emit({ type: "session_switch", reason: "resume", previousSessionFile: undefined });
			await sessionA.runner.emit({ type: "session_switch", reason: "resume", previousSessionFile: undefined });
			const preparedA = await sessionA.invokeModel("back to A", BASE_PROMPT);
			const preparedB = await sessionB.invokeModel("on B", BASE_PROMPT);

			// Then
			expect({
				distinct: sessionA.sessionManager.getSessionId() !== sessionB.sessionManager.getSessionId(),
				evaluations: await startupEvaluations(logPath),
				aContext: blockText(preparedA).includes("CONTEXT_A_TOKEN"),
				aStale: blockText(preparedA).includes("STALE_A_TOKEN"),
				bContext: blockText(preparedB).includes("CONTEXT_B_TOKEN"),
				bLeak: blockText(preparedB).includes("CONTEXT_A_TOKEN"),
			}).toEqual({
				distinct: true,
				evaluations: 2,
				aContext: true,
				aStale: false,
				bContext: true,
				bLeak: false,
			});
		}, 30000);

		test.each([
			["session switch", { type: "session_switch", reason: "new", previousSessionFile: undefined }],
			["session branch", { type: "session_branch", previousSessionFile: undefined }],
			["session tree", { type: "session_tree", newLeafId: null, oldLeafId: null }],
		] as const)("%s navigation clears pending advice and the continuation cap but keeps startup context", async (_name, navigation) => {
			// Given
			const session = await open();
			configureFakeResponse({ context: "KEPT_STARTUP_TOKEN" });
			await session.runner.emit({ type: "session_start" });
			await stageGuidance(session, "PENDING_ADVICE_TOKEN");
			configureFakeResponse({ continue: true, additionalContext: "CONTINUE_TOKEN" });
			await requestContinuations(session, 8);

			// When
			configureFakeResponse({});
			await session.runner.emit(navigation);
			configureFakeResponse({ continue: true, additionalContext: "CONTINUE_TOKEN" });
			const fresh = await collectContinuationFlags(session, 8, 20);
			const prepared = await session.invokeModel("after navigation", BASE_PROMPT);

			// Then
			expect({
				fresh,
				startup: blockText(prepared).includes("KEPT_STARTUP_TOKEN"),
				advice: blockText(prepared).includes("PENDING_ADVICE_TOKEN"),
				evaluations: await startupEvaluations(logPath),
			}).toEqual({ fresh: FULL_CONTINUATION_BUDGET, startup: true, advice: false, evaluations: 1 });
		}, 30000);

		test("a repeated session_start does not reset a live continuation cap", async () => {
			// Given
			const session = await open();
			await session.runner.emit({ type: "session_start" });
			configureFakeResponse({ continue: true, additionalContext: "CONTINUE_TOKEN" });
			await requestContinuations(session, 8);

			// When
			await session.runner.emit({ type: "session_start" });
			const ninth = await emitStop(session, { turnId: 9 });

			// Then
			expect(ninth).toBeUndefined();
		}, 30000);

		test("two factories in one process keep their sessions isolated", async () => {
			// Given
			const first = await open();
			const second = await open();
			configureFakeResponse({ context: "FIRST_FACTORY_TOKEN" });
			await first.runner.emit({ type: "session_start" });
			configureFakeResponse({ context: "SECOND_FACTORY_TOKEN" });
			await second.runner.emit({ type: "session_start" });
			configureFakeResponse({ continue: true, additionalContext: "CONTINUE_TOKEN" });
			await requestContinuations(first, 8);

			// When
			const exhausted = await emitStop(first, { turnId: 9 });
			const independent = await collectContinuationFlags(second, 8, 20);
			configureFakeResponse({});
			const preparedFirst = await first.invokeModel("first", BASE_PROMPT);
			const preparedSecond = await second.invokeModel("second", BASE_PROMPT);

			// Then
			expect({
				exhausted,
				independent,
				firstOnly: blockText(preparedFirst).includes("FIRST_FACTORY_TOKEN")
					&& !blockText(preparedFirst).includes("SECOND_FACTORY_TOKEN"),
				secondOnly: blockText(preparedSecond).includes("SECOND_FACTORY_TOKEN")
					&& !blockText(preparedSecond).includes("FIRST_FACTORY_TOKEN"),
			}).toEqual({ exhausted: undefined, independent: FULL_CONTINUATION_BUDGET, firstOnly: true, secondOnly: true });
		}, 30000);

		test("session shutdown clears every session's state", async () => {
			// Given
			const session = await open();
			configureFakeResponse({ context: "SHUTDOWN_STARTUP_TOKEN" });
			await session.runner.emit({ type: "session_start" });
			configureFakeResponse({});

			// When
			await session.runner.emit({ type: "session_shutdown" });
			const prepared = await session.invokeModel("after shutdown", BASE_PROMPT);

			// Then
			expect(prepared).toEqual(BASE_PROMPT);
		}, 30000);
	});
}
