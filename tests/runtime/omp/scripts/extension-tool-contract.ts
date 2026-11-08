import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, test } from "bun:test";
import { appendFile, rm } from "node:fs/promises";
import * as path from "node:path";

import type { BashToolInput } from "@oh-my-pi/pi-coding-agent/tools/bash";

import { createRuntimeHarness, type RuntimeHarness } from "./runtime-harness.ts";
import {
	clearRuntimeEnvironment,
	configureFakeFailure,
	configureFakeResponse,
	configureRuntimeEnvironment,
	createRecordPath,
	createTemporaryRoot,
	FIXED_SESSION_ID,
	loadBashVariants,
	readRecordedPayload,
	WORKSPACE_ROOT,
} from "./runtime-test-support.ts";

const BASH_VARIANTS = (await loadBashVariants()).map((input, index) => [`variant-${index + 1}`, input] as const);

type UserSurface = "bash" | "python";

type UserSurfaceOutcome =
	| { readonly kind: "blocked"; readonly output: string }
	| { readonly kind: "executed" };

class HarnessStateError extends Error {
	constructor() {
		super("Extension tool harness is unavailable");
		this.name = "HarnessStateError";
	}
}

function requireHarness(harness: RuntimeHarness | undefined): RuntimeHarness {
	if (harness === undefined) throw new HarnessStateError();
	return harness;
}

async function emitUserSurface(harness: RuntimeHarness, surface: UserSurface) {
	switch (surface) {
		case "bash":
			return await harness.runner.emitUserBash({
				type: "user_bash",
				command: "printf sentinel",
				excludeFromContext: false,
				cwd: ".",
			});
		case "python":
			return await harness.runner.emitUserPython({
				type: "user_python",
				code: 'print("sentinel")',
				excludeFromContext: false,
				cwd: ".",
			});
	}
}

async function executeUserSurface(
	harness: RuntimeHarness,
	surface: UserSurface,
	sentinel: string,
): Promise<UserSurfaceOutcome> {
	const interception = await emitUserSurface(harness, surface);
	if (interception?.result !== undefined) {
		return { kind: "blocked", output: interception.result.output };
	}
	await appendFile(sentinel, `${surface}\n`, "utf8");
	return { kind: "executed" };
}

async function executeWriteSurface(harness: RuntimeHarness, sentinel: string): Promise<UserSurfaceOutcome> {
	const interception = await harness.runner.emitToolCall({
		type: "tool_call",
		toolCallId: "write-tool-call-fixed",
		toolName: "write",
		input: { path: sentinel, content: "write sentinel" },
	});
	if (interception?.block) return { kind: "blocked", output: interception.reason ?? "Blocked by extension" };
	await appendFile(sentinel, "write\n", "utf8");
	return { kind: "executed" };
}

export function registerExtensionToolContractTests(): void {
	describe("staged OMP tool contract", () => {
		const temporaryPaths: string[] = [];
		let harness: RuntimeHarness | undefined;

		beforeAll(() => {
			configureRuntimeEnvironment();
		});

		// Startup runs once per session identity, so each test owns a fresh session.
		beforeEach(async () => {
			configureFakeResponse({});
			process.env.SLOPGATE_SESSION_ID = FIXED_SESSION_ID;
			delete process.env.SLOPGATE_OMP_INPUT_REWRITE;
			harness = await createRuntimeHarness();
		});

		afterEach(async () => {
			await harness?.close();
			harness = undefined;
			await Promise.all(temporaryPaths.splice(0).map(root => rm(root, { recursive: true, force: true })));
		});

		afterAll(() => {
			clearRuntimeEnvironment();
		});

		test("forwards the literal runner context and fixed identity", async () => {
			// Given
			const root = await createTemporaryRoot("slopgate-omp-payload-");
			temporaryPaths.push(root);
			const recordPath = await createRecordPath(root, "session-start.json");

			// When
			const activeHarness = requireHarness(harness);
			await activeHarness.runner.emit({ type: "session_start" });
			const payload = await readRecordedPayload(recordPath);
			const native = Object.keys(payload);

			// Then
			expect(payload).toMatchObject({
				hook_event_name: "session_start",
				cwd: ".",
				session_id: FIXED_SESSION_ID,
				tool_call_id: "",
				tool_name: "",
			});
			expect(native).not.toContain("omp_event");
			expect(native).not.toContain("tool_response");
			expect(path.resolve(activeHarness.runner.cwd)).toBe(WORKSPACE_ROOT);
		}, 30000);

		test.each(BASH_VARIANTS)("records normalized input equal to executed args for %s with rewrite default off", async (name, input) => {
			// Given
			const root = await createTemporaryRoot(`slopgate-omp-bash-${name}-`);
			temporaryPaths.push(root);
			configureFakeResponse({ updated_input: { command: "printf rewritten" } });
			const recordPath = await createRecordPath(root, "stdin.json");

			// When
			const outcome = await requireHarness(harness).executeBash(input);
			const payload = await readRecordedPayload(recordPath);

			// Then
			expect({ normalized: payload.tool_input, outcome }).toEqual({
				normalized: input,
				outcome: { kind: "executed", input },
			});
		}, 30000);

		test("applies a proven bash rewrite when the feature flag is enabled", async () => {
			// Given
			const original: BashToolInput = { command: "printf original", cwd: ".", env: { CONTRACT: "1" } };
			const rewritten: BashToolInput = { command: "printf rewritten", cwd: ".", env: { CONTRACT: "2" } };
			process.env.SLOPGATE_OMP_INPUT_REWRITE = "1";
			configureFakeResponse({ updated_input: rewritten });

			// When
			const outcome = await requireHarness(harness).executeBash(original);

			// Then
			expect(outcome).toEqual({ kind: "executed", input: rewritten });
		}, 30000);

	test.each([
		["unknown field", { command: "printf attack", shell: "echo pwned" }],
		["missing command", { cwd: "." }],
	] as const)("refuses a returned rewrite with %s and preserves execution args", async (_name, updatedInput) => {
		// Given
		const original: BashToolInput = { command: "printf safe" };
		process.env.SLOPGATE_OMP_INPUT_REWRITE = "1";
		configureFakeResponse({ updated_input: updatedInput });

		// When
		const outcome = await requireHarness(harness).executeBash(original);

		// Then
		expect(outcome).toEqual({ kind: "executed", input: original });
	}, 30000);

	test("refuses a returned bash rewrite with non-string env members before execution", async () => {
		// Given
		const root = await createTemporaryRoot("slopgate-omp-returned-env-");
		temporaryPaths.push(root);
		const original: BashToolInput = { command: "printf safe" };
		process.env.SLOPGATE_OMP_INPUT_REWRITE = "1";
		configureFakeResponse({ updated_input: { command: "printf attack", env: { TOKEN: 1 } } });
		const recordPath = await createRecordPath(root, "stdin.json");
		const activeHarness = requireHarness(harness);
		const executionStart = activeHarness.bashTool.observedExecutions.length;

		// When
		const outcome = await activeHarness.executeObservedBash(original, "returned-env-member-fixed");
		const payload = await readRecordedPayload(recordPath);

		// Then
		expect({
			executions: activeHarness.bashTool.observedExecutions.slice(executionStart),
			classified: {
				event: payload.hook_event_name,
				toolName: payload.tool_name,
				toolCallId: payload.tool_call_id,
				nativeInput: payload.input,
			},
			legacy: ["omp_event", "tool_response"].filter(key => key in payload),
			normalized: payload.tool_input,
			outcome,
		}).toEqual({
			executions: [original],
			classified: {
				event: "tool_call",
				toolName: "bash",
				toolCallId: "returned-env-member-fixed",
				nativeInput: original,
			},
			legacy: [],
			normalized: original,
			outcome: { input: original, kind: "executed", rewriteApplied: false },
		});
	}, 30000);

	test("refuses a non-object returned rewrite and preserves execution args", async () => {
		// Given
		const original: BashToolInput = { command: "printf safe" };
		process.env.SLOPGATE_OMP_INPUT_REWRITE = "1";
		configureFakeResponse({ updated_input: "printf attack" });

		// When
		const outcome = await requireHarness(harness).executeBash(original);

		// Then
		expect(outcome).toEqual({ kind: "executed", input: original });
	}, 30000);

	test("refuses rewrite for non-object observed bash input and forwards original args", async () => {
		// Given
		const root = await createTemporaryRoot("slopgate-omp-observed-non-object-");
		temporaryPaths.push(root);
		const original = "printf malformed";
		process.env.SLOPGATE_OMP_INPUT_REWRITE = "1";
		configureFakeResponse({ updated_input: { command: "printf rewritten" } });
		const recordPath = await createRecordPath(root, "stdin.json");
		const activeHarness = requireHarness(harness);
		const executionStart = activeHarness.bashTool.observedExecutions.length;

		// When
		const outcome = await activeHarness.executeObservedBash(original, "observed-non-object-fixed");
		const payload = await readRecordedPayload(recordPath);

		// Then
		expect({
			executions: activeHarness.bashTool.observedExecutions.slice(executionStart),
			classified: {
				event: payload.hook_event_name,
				toolName: payload.tool_name,
				toolCallId: payload.tool_call_id,
				nativeInput: payload.input,
			},
			legacy: ["omp_event", "tool_response"].filter(key => key in payload),
			normalized: payload.tool_input,
			outcome,
		}).toEqual({
			executions: [original],
			classified: {
				event: "tool_call",
				toolName: "bash",
				toolCallId: "observed-non-object-fixed",
				nativeInput: original,
			},
			legacy: [],
			normalized: {},
			outcome: { input: original, kind: "executed", rewriteApplied: false },
		});
	}, 30000);

	test.each([
		["wrong command type", { command: 7 }],
		["extra key", { command: "printf safe", derived: true }],
		["missing command", { cwd: "." }],
		["wrong optional field type", { command: "printf safe", timeout: "30" }],
	] as const)("refuses rewrite when observed bash input has %s", async (_name, input) => {
		const toolName: string = "bash";
		process.env.SLOPGATE_OMP_INPUT_REWRITE = "1";
		configureFakeResponse({ updated_input: { command: "printf rewritten" } });
		const result = await requireHarness(harness).runner.emitToolCall({
			type: "tool_call",
			toolCallId: "malformed-bash-fixed",
			toolName,
			input,
		});
		expect(result).toBeUndefined();
	}, 30000);

	test("refuses an edit echo attack even when rewrite is enabled", async () => {
		const normalizedEdit = { path: "target.txt", content: "safe", derived: "gate-only" };
		process.env.SLOPGATE_OMP_INPUT_REWRITE = "1";
		configureFakeResponse({ updated_input: normalizedEdit });
		const result = await requireHarness(harness).runner.emitToolCall({
			type: "tool_call",
			toolCallId: "edit-echo-fixed",
			toolName: "edit",
			input: normalizedEdit,
		});
		expect(result).toBeUndefined();
	}, 30000);

		test("blocks protected edit envelopes under native edit dispatch", async () => {
			// Given
			const activeHarness = requireHarness(harness)
			const patchText = [
				"*** Begin Patch",
				"*** Update File: slopgate.toml",
				"@@",
				"-enabled = true",
				"+enabled = false",
				"*** Update File: safe.txt",
				"@@",
				"-safe",
				"+safer",
				"*** End Patch",
			].join("\n")

			// When
			const result = await activeHarness.runner.emitToolCall({
				type: "tool_call",
				toolCallId: "apply-patch-protected-fixed",
				toolName: "edit",
				input: { input: patchText },
			})

			// Then
			expect(result).toEqual({
				block: true,
				reason: "Cannot modify Slopgate infrastructure: slopgate.toml",
			})
		}, 30000)

		test("blocks protected apply_patch wire-alias envelopes", async () => {
			const result = await requireHarness(harness).runner.emitToolCall({
				type: "tool_call",
				toolCallId: "apply-patch-alias-protected-fixed",
				toolName: "apply_patch",
				input: { input: "*** Update File: slopgate.toml\n@@\n-enabled = true\n+enabled = false" },
			})
			expect(result).toEqual({
				block: true,
				reason: "Cannot modify Slopgate infrastructure: slopgate.toml",
			})
		}, 30000)

		test("blocks protected single-file hashline edits before execution", async () => {
			const result = await requireHarness(harness).runner.emitToolCall({
				type: "tool_call",
				toolCallId: "hashline-single-protected-fixed",
				toolName: "edit",
				input: { input: "[slopgate.toml#a1b2]\n+enabled = false" },
			})
			expect(result).toEqual({
				block: true,
				reason: "Cannot modify Slopgate infrastructure: slopgate.toml",
			})
		}, 30000)

		test("blocks protected targets in multi-file hashline edits", async () => {
			const envelope = ["[safe.md#aaaa]", "+docs", "", "[slopgate.toml#fffe]", "+enabled = false"].join("\n")
			const result = await requireHarness(harness).runner.emitToolCall({
				type: "tool_call",
				toolCallId: "hashline-multi-protected-fixed",
				toolName: "edit",
				input: { input: envelope },
			})
			expect(result).toEqual({
				block: true,
				reason: "Cannot modify Slopgate infrastructure: slopgate.toml",
			})
		}, 30000)

		test("blocks protected targets from native derived path fields", async () => {
			const result = await requireHarness(harness).runner.emitToolCall({
				type: "tool_call",
				toolCallId: "hashline-derived-paths-fixed",
				toolName: "edit",
				input: {
					input: "¶slopgate.toml#a1b2\n+enabled = false",
					path: "slopgate.toml",
					paths: ["slopgate.toml"],
				},
			})
			expect(result).toEqual({
				block: true,
				reason: "Cannot modify Slopgate infrastructure: slopgate.toml",
			})
		}, 30000)

		test("does not block bracketed prose in edit bodies", async () => {
			const result = await requireHarness(harness).runner.emitToolCall({
				type: "tool_call",
				toolCallId: "hashline-prose-unprotected-fixed",
				toolName: "edit",
				input: { input: "update notes about [slopgate.toml] header formatting" },
			})
			expect(result).toBeUndefined()
		}, 30000)

		test("blocks the Write tool before its sentinel is created", async () => {
			// Given
			const root = await createTemporaryRoot("slopgate-omp-blocked-");
			temporaryPaths.push(root);
			const sentinel = path.join(root, "sentinel.log");
			configureFakeResponse({ block: true, reason: "fixture denial" });

			// When
			const outcome = await executeWriteSurface(requireHarness(harness), sentinel);

			// Then
			expect(outcome).toEqual({ kind: "blocked", output: "fixture denial" });
			expect(await Bun.file(sentinel).exists()).toBe(false);
		}, 30000);

		test("executes the allowed Write tool exactly once", async () => {
			// Given
			const root = await createTemporaryRoot("slopgate-omp-allowed-");
			temporaryPaths.push(root);
			const sentinel = path.join(root, "sentinel.log");

			// When
			const outcome = await executeWriteSurface(requireHarness(harness), sentinel);

			// Then
			expect(outcome).toEqual({ kind: "executed" });
			expect(await Bun.file(sentinel).text()).toBe("write\n");
		}, 30000);

		test.each(["bash", "python"] as const)("blocks %s before its host sentinel executes", async surface => {
			// Given
			const root = await createTemporaryRoot(`slopgate-omp-user-${surface}-blocked-`);
			temporaryPaths.push(root);
			const sentinel = path.join(root, "sentinel.log");
			configureFakeResponse({ block: true, reason: `${surface} denied` });

			// When
			const outcome = await executeUserSurface(requireHarness(harness), surface, sentinel);

			// Then
			expect(outcome).toEqual({ kind: "blocked", output: `${surface} denied` });
			expect(await Bun.file(sentinel).exists()).toBe(false);
		}, 30000);

		test.each(["bash", "python"] as const)("executes the allowed %s host sentinel exactly once", async surface => {
			// Given
			const root = await createTemporaryRoot(`slopgate-omp-user-${surface}-allowed-`);
			temporaryPaths.push(root);
			const sentinel = path.join(root, "sentinel.log");

			// When
			const outcome = await executeUserSurface(requireHarness(harness), surface, sentinel);

			// Then
			expect(outcome).toEqual({ kind: "executed" });
			expect(await Bun.file(sentinel).text()).toBe(`${surface}\n`);
		}, 30000);

		test.each([
		["invalid JSON", "not-json", 0],
		["subprocess failure", "", 17],
	] as const)("fails closed in a managed repo and open outside for %s", async (_name, stdout, exitCode) => {
			// Given
			configureFakeFailure(stdout, exitCode);
			const outsideRoot = await createTemporaryRoot("slopgate-omp-outside-");
			temporaryPaths.push(outsideRoot);
			const outsideHarness = await createRuntimeHarness({ cwd: outsideRoot });

			// When
			const managed = await requireHarness(harness).executeBash({ command: "printf managed" });
			const outside = await outsideHarness.executeBash({ command: "printf outside" });
			await outsideHarness.close();

			// Then
			expect(managed.kind).toBe("blocked");
			expect(outside.kind).toBe("executed");
		}, 30000);
	});
}
