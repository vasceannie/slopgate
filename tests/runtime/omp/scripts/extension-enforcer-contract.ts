import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, spyOn, test } from "bun:test";
import { rm } from "node:fs/promises";
import * as path from "node:path";

import { logger } from "@oh-my-pi/pi-utils";

import { createRuntimeHarness, type RuntimeHarness } from "./runtime-harness.ts";
import {
	clearRuntimeEnvironment,
	collectContinuationFlags,
	configureFakeFailure,
	configureFakeMode,
	configureFakeResponse,
	configureRuntimeEnvironment,
	createTemporaryRoot,
	emitStop,
	FIXED_SESSION_ID,
	isProcessAlive,
	readHangingPids,
	type HangingPids,
} from "./runtime-test-support.ts";

type LogEvent = Parameters<Parameters<typeof logger.registerLogSink>[0]>[0];

const BASE_PROMPT = ["BASE_SYSTEM_TOKEN"];
const SHORT_TIMEOUT_MS = "300";
const OVERSIZED_PAYLOAD_BYTES = 8 * 1024 * 1024;
const FULL_CONTINUATION_BUDGET = [true, true, true, true, true, true, true, true] as const;
const LOGGED_FIELDS = ["category", "event", "exit_code", "service", "session_id"] as const;

class EnforcerHarnessStateError extends Error {
	constructor() {
		super("Enforcer contract harness is unavailable");
		this.name = "EnforcerHarnessStateError";
	}
}

function requireHarness(harness: RuntimeHarness | undefined): RuntimeHarness {
	if (harness === undefined) throw new EnforcerHarnessStateError();
	return harness;
}

function readToolCall(harness: RuntimeHarness, toolCallId: string, input: Record<string, unknown> = { path: "README.md" }) {
	return harness.runner.emitToolCall({ type: "tool_call", toolCallId, toolName: "read", input });
}

function expectReaped(pids: HangingPids): void {
	expect({
		child: isProcessAlive(pids.child),
		grandchild: isProcessAlive(pids.grandchild),
	}).toEqual({ child: false, grandchild: false });
}

export function registerExtensionEnforcerContractTests(): void {
	describe("staged OMP enforcer process contract", () => {
		const extraHarnesses: RuntimeHarness[] = [];
		const extraRoots: string[] = [];
		let harness: RuntimeHarness | undefined;
		let temporaryRoot: string | undefined;
		let pidsPath = "";

		beforeAll(() => {
			configureRuntimeEnvironment();
		});

		beforeEach(async () => {
			configureFakeResponse({});
			process.env.SLOPGATE_SESSION_ID = FIXED_SESSION_ID;
			temporaryRoot = await createTemporaryRoot("slopgate-omp-enforcer-");
			pidsPath = path.join(temporaryRoot, "pids.json");
			process.env.SLOPGATE_FAKE_PIDS_PATH = pidsPath;
			harness = await createRuntimeHarness({ withUI: true });
		});

		afterEach(async () => {
			try {
				await harness?.close();
				await Promise.all(extraHarnesses.splice(0).map(extra => extra.close()));
			} finally {
				harness = undefined;
				configureFakeMode(undefined);
				delete process.env.SLOPGATE_ENFORCER_TIMEOUT_MS;
				delete process.env.SLOPGATE_FAKE_PIDS_PATH;
				await Promise.all(extraRoots.splice(0).map(root => rm(root, { recursive: true, force: true })));
				if (temporaryRoot !== undefined) await rm(temporaryRoot, { recursive: true, force: true });
				temporaryRoot = undefined;
			}
		});

		afterAll(() => {
			clearRuntimeEnvironment();
		});

		const openUnmanaged = async (): Promise<RuntimeHarness> => {
			const outsideRoot = await createTemporaryRoot("slopgate-omp-unmanaged-");
			extraRoots.push(outsideRoot);
			const outside = await createRuntimeHarness({ cwd: outsideRoot, withUI: true });
			extraHarnesses.push(outside);
			return outside;
		};

		test("a hung enforcer times out, kills its whole process tree, and fails closed only when managed", async () => {
			// Given
			process.env.SLOPGATE_ENFORCER_TIMEOUT_MS = SHORT_TIMEOUT_MS;
			configureFakeMode("hang");
			const unmanaged = await openUnmanaged();

			// When
			const managedResult = await readToolCall(requireHarness(harness), "hung-managed");
			const managedPids = await readHangingPids(pidsPath);
			await rm(pidsPath, { force: true });
			const unmanagedResult = await readToolCall(unmanaged, "hung-unmanaged");
			const unmanagedPids = await readHangingPids(pidsPath);

			// Then
			expect(managedResult?.block).toBe(true);
			expect(managedResult?.reason).toContain("timed out");
			expect(unmanagedResult).toBeUndefined();
			expectReaped(managedPids);
			expectReaped(unmanagedPids);
		}, 30000);

		test("a non-positive or non-numeric timeout override falls back to the default", async () => {
			// Given
			process.env.SLOPGATE_ENFORCER_TIMEOUT_MS = "not-a-number";
			configureFakeResponse({ context: "TIMEOUT_FALLBACK_TOKEN" });

			// When
			await requireHarness(harness).runner.emit({ type: "session_start" });
			const prepared = await requireHarness(harness).invokeModel("next", BASE_PROMPT);

			// Then
			expect(prepared[1]).toContain("TIMEOUT_FALLBACK_TOKEN");
		}, 30000);

		test("an enforcer that closes stdin early loses the payload and never becomes an allow", async () => {
			// Given
			configureFakeMode("ignore-stdin");
			const unmanaged = await openUnmanaged();
			const oversized = { command: "x".repeat(OVERSIZED_PAYLOAD_BYTES) };

			// When
			const managedResult = await requireHarness(harness).runner.emitToolCall({
				type: "tool_call",
				toolCallId: "early-close-managed",
				toolName: "read",
				input: oversized,
			});
			const unmanagedResult = await unmanaged.runner.emitToolCall({
				type: "tool_call",
				toolCallId: "early-close-unmanaged",
				toolName: "read",
				input: oversized,
			});

			// Then
			expect(managedResult?.block).toBe(true);
			expect(managedResult?.reason).toContain("did not read its input");
			expect(unmanagedResult).toBeUndefined();
		}, 60000);

		test.each([
			["nonzero exit", "", 17],
			["invalid JSON", "not-json", 0],
		] as const)("%s fails closed in a managed repo and is a no-op unmanaged", async (_name, stdout, exitCode) => {
			// Given
			configureFakeFailure(stdout, exitCode);
			const unmanaged = await openUnmanaged();

			// When
			const managedResult = await readToolCall(requireHarness(harness), "failure-managed");
			const unmanagedResult = await readToolCall(unmanaged, "failure-unmanaged");

			// Then
			expect(managedResult?.block).toBe(true);
			expect(unmanagedResult).toBeUndefined();
		}, 30000);

		test("empty stdout on a clean exit means no findings", async () => {
			// Given
			configureFakeFailure("", 0);

			// When
			const result = await readToolCall(requireHarness(harness), "empty-success");

			// Then
			expect(result).toBeUndefined();
		}, 30000);

		test("an aborted session_stop reaps the child and adds no guidance or continuation use", async () => {
			// Given
			const activeHarness = requireHarness(harness);
			configureFakeMode("hang");
			const controller = new AbortController();
			const pending = emitStop(activeHarness, { signal: controller.signal });
			const pids = await readHangingPids(pidsPath);

			// When
			controller.abort();
			const result = await pending;
			configureFakeMode(undefined);
			configureFakeResponse({ continue: true, additionalContext: "CONTINUE_TOKEN" });
			const fresh = await collectContinuationFlags(activeHarness, 8, 20);
			configureFakeResponse({});
			const prepared = await activeHarness.invokeModel("after abort", BASE_PROMPT);

			// Then
			expect(result).toBeUndefined();
			expectReaped(pids);
			expect(fresh).toEqual(FULL_CONTINUATION_BUDGET);
			expect(prepared).toEqual(BASE_PROMPT);
			expect(activeHarness.notifications).toEqual([]);
		}, 30000);

		test("session shutdown reaps an in-flight child without a degraded result, and later work still runs", async () => {
			// Given
			const activeHarness = requireHarness(harness);
			configureFakeMode("hang");
			const pending = readToolCall(activeHarness, "shutdown-inflight");
			const pids = await readHangingPids(pidsPath);

			// When
			await activeHarness.runner.emit({ type: "session_shutdown" });
			const result = await pending;
			configureFakeMode(undefined);
			configureFakeResponse({ context: "AFTER_SHUTDOWN_TOKEN" });
			await readToolCall(activeHarness, "after-shutdown");
			const merged = await activeHarness.runner.emitToolResult({
				type: "tool_result",
				toolCallId: "after-shutdown",
				toolName: "custom",
				input: {},
				content: [{ type: "text", text: "native output" }],
				isError: false,
			});

			// Then
			expect(result).toBeUndefined();
			expectReaped(pids);
			expect(merged?.content?.at(-1)).toEqual({ type: "text", text: "Slopgate findings:\nAFTER_SHUTDOWN_TOKEN" });
		}, 30000);

		test("a cancelled tool_result adds nothing from the enforcer and still discards the stored entry", async () => {
			// Given
			const activeHarness = requireHarness(harness);
			configureFakeResponse({ context: "STORED_PRE_TOKEN" });
			await readToolCall(activeHarness, "cancelled-result");
			configureFakeMode("hang");
			const pending = activeHarness.runner.emitToolResult({
				type: "tool_result",
				toolCallId: "cancelled-result",
				toolName: "custom",
				input: {},
				content: [{ type: "text", text: "native output" }],
				isError: false,
			});
			const pids = await readHangingPids(pidsPath);

			// When
			await activeHarness.runner.emit({ type: "session_shutdown" });
			const cancelled = await pending;
			configureFakeMode(undefined);
			configureFakeFailure("", 0);
			const duplicate = await activeHarness.runner.emitToolResult({
				type: "tool_result",
				toolCallId: "cancelled-result",
				toolName: "custom",
				input: {},
				content: [{ type: "text", text: "native output" }],
				isError: false,
			});

			// Then
			expect({ cancelled, duplicate }).toEqual({ cancelled: undefined, duplicate: undefined });
			expectReaped(pids);
		}, 30000);

		test("a headless denied input returns handled and writes the stderr reason with no custom message", async () => {
			// Given
			const headless = await createRuntimeHarness();
			extraHarnesses.push(headless);
			const writes: string[] = [];
			const stderrSpy = spyOn(process.stderr, "write").mockImplementation((chunk: string | Uint8Array) => {
				writes.push(typeof chunk === "string" ? chunk : new TextDecoder().decode(chunk));
				return true;
			});
			configureFakeResponse({ block: true, reason: "HEADLESS_DENY_TOKEN" });

			// When
			let result: Awaited<ReturnType<typeof headless.runner.emitInput>>;
			try {
				result = await headless.runner.emitInput("denied", undefined, "extension");
			} finally {
				stderrSpy.mockRestore();
			}

			// Then
			expect(result).toEqual({ handled: true });
			expect(writes).toContain("[slopgate] input blocked: HEADLESS_DENY_TOKEN\n");
			expect(headless.sendMessageCalls).toBe(0);
		}, 30000);

		test("failure logging carries bounded structured fields only", async () => {
			// Given
			configureFakeFailure("not-json", 0);
			const events: LogEvent[] = [];
			const dispose = logger.registerLogSink(event => {
				events.push(event);
			});

			// When
			try {
				await readToolCall(requireHarness(harness), "logging-call", { path: "SECRET_PROMPT_CONTENT" });
			} finally {
				dispose();
			}

			// Then
			const slopgateEvents = events.filter(event => event.context?.service === "slopgate");
			expect(slopgateEvents).toHaveLength(1);
			const context = slopgateEvents[0]?.context ?? {};
			expect(Object.keys(context).toSorted()).toEqual([...LOGGED_FIELDS]);
			expect(context).toMatchObject({ service: "slopgate", event: "tool_call", category: "invalid_json", exit_code: 0 });
			expect(JSON.stringify(slopgateEvents)).not.toContain("SECRET_PROMPT_CONTENT");
		}, 30000);
	});
}
