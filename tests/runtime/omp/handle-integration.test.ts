import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { mkdir, rm } from "node:fs/promises";
import * as path from "node:path";

import { createRuntimeHarness, type RuntimeHarness } from "./scripts/runtime-harness.ts";
import {
	assistantTextMessage,
	createRecordPath,
	createTemporaryRoot,
	emitStop,
	FAKE_ENFORCER,
	readRecordedPayload,
} from "./scripts/runtime-test-support.ts";

const REAL_SLOPGATE = path.resolve(import.meta.dir, "../../../.venv/bin/slopgate");
const ENVIRONMENT_KEYS = [
	"HOME",
	"XDG_CONFIG_HOME",
	"XDG_DATA_HOME",
	"XDG_STATE_HOME",
	"SLOPGATE_BIN",
	"SLOPGATE_CONFIG",
	"SLOPGATE_CONFIG_DIR",
	"SLOPGATE_ROOT",
	"SLOPGATE_DAEMON_SOCKET",
	"SLOPGATE_SESSION_ID",
	"SLOPGATE_FAKE_REAL_BIN",
	"SLOPGATE_FAKE_RECORD_PATH",
	"SLOPGATE_FAKE_RESPONSE",
	"SLOPGATE_FAKE_STDOUT",
	"SLOPGATE_FAKE_EXIT_CODE",
	"CLAUDE_HOOK_LAYER_ROOT",
	"HOOK_LAYER_ROOT",
] as const;

const environmentSnapshot = new Map<string, string | undefined>();
let harness: RuntimeHarness | undefined;
let temporaryRoot: string | undefined;
let recordPath: string | undefined;

class HandleHarnessStateError extends Error {
	constructor(detail: string) {
		super(`Real CLI handle harness is unavailable: ${detail}`);
		this.name = "HandleHarnessStateError";
	}
}

function requireHarness(): RuntimeHarness {
	if (harness === undefined) throw new HandleHarnessStateError("runtime");
	return harness;
}

function requireRecordPath(): string {
	if (recordPath === undefined) throw new HandleHarnessStateError("record path");
	return recordPath;
}

function requireTemporaryRoot(): string {
	if (temporaryRoot === undefined) throw new HandleHarnessStateError("temporary root");
	return temporaryRoot;
}

function isRecord(value: unknown): value is Readonly<Record<string, unknown>> {
	return typeof value === "object" && value !== null && !Array.isArray(value);
}

async function runRealHandle(
	payload: Readonly<Record<string, unknown>>,
	environment: Readonly<Record<string, string>> = {},
): Promise<Readonly<Record<string, unknown>>> {
	const child = Bun.spawn([REAL_SLOPGATE, "handle", "--platform", "omp"], {
		cwd: import.meta.dir,
		env: { ...process.env, ...environment },
		stdin: new Blob([JSON.stringify(payload)]),
		stdout: "pipe",
		stderr: "pipe",
	});
	const [exitCode, stdout, stderr] = await Promise.all([
		child.exited,
		new Response(child.stdout).text(),
		new Response(child.stderr).text(),
	]);
	if (exitCode !== 0) throw new HandleHarnessStateError(`handle exited ${exitCode}: ${stderr}`);
	const parsed: unknown = JSON.parse(stdout);
	if (!isRecord(parsed)) throw new HandleHarnessStateError("handle output was not an object");
	return parsed;
}

async function readRuleIds(root: string): Promise<readonly string[]> {
	const rulesPath = path.join(root, "state/logs/rules.jsonl");
	const contents = await Bun.file(rulesPath).text();
	const ruleIds: string[] = [];
	for (const line of contents.split("\n")) {
		if (line.length === 0) continue;
		const parsed: unknown = JSON.parse(line);
		if (isRecord(parsed) && typeof parsed.rule_id === "string") ruleIds.push(parsed.rule_id);
	}
	return ruleIds;
}

function setIsolatedEnvironment(root: string, sessionId: string): void {
	process.env.HOME = path.join(root, "home");
	process.env.XDG_CONFIG_HOME = path.join(root, "xdg-config");
	process.env.XDG_DATA_HOME = path.join(root, "xdg-data");
	process.env.XDG_STATE_HOME = path.join(root, "xdg-state");
	process.env.SLOPGATE_BIN = FAKE_ENFORCER;
	process.env.SLOPGATE_CONFIG_DIR = path.join(root, "config");
	process.env.SLOPGATE_ROOT = path.join(root, "state");
	process.env.SLOPGATE_SESSION_ID = sessionId;
	process.env.SLOPGATE_FAKE_REAL_BIN = REAL_SLOPGATE;
	for (const key of [
		"SLOPGATE_CONFIG",
		"SLOPGATE_DAEMON_SOCKET",
		"SLOPGATE_FAKE_RESPONSE",
		"SLOPGATE_FAKE_STDOUT",
		"SLOPGATE_FAKE_EXIT_CODE",
		"CLAUDE_HOOK_LAYER_ROOT",
		"HOOK_LAYER_ROOT",
	] as const) {
		delete process.env[key];
	}
}

beforeEach(async () => {
	for (const key of ENVIRONMENT_KEYS) environmentSnapshot.set(key, process.env[key]);
	temporaryRoot = await createTemporaryRoot("slopgate-omp-real-cli-");
	setIsolatedEnvironment(temporaryRoot, `omp-real-${crypto.randomUUID()}`);
	recordPath = await createRecordPath(temporaryRoot, "stdin.json");
	harness = await createRuntimeHarness();
	await harness.runner.emit({ type: "session_start" });
});

afterEach(async () => {
	await harness?.close();
	if (temporaryRoot !== undefined) await rm(temporaryRoot, { recursive: true, force: true });
	harness = undefined;
	temporaryRoot = undefined;
	recordPath = undefined;
	for (const key of ENVIRONMENT_KEYS) {
		const value = environmentSnapshot.get(key);
		if (value === undefined) delete process.env[key];
		else process.env[key] = value;
	}
	environmentSnapshot.clear();
});

describe("staged OMP bridge with the real Slopgate CLI", () => {
	test("real cmd_handle denies a protected Write payload", async () => {
		// Given
		const fixturePath = path.resolve(import.meta.dir, "../../fixtures/omp/18.0.5/tool-call-write.json");
		const fixture: unknown = JSON.parse(await Bun.file(fixturePath).text());
		if (!isRecord(fixture)) throw new HandleHarnessStateError("write fixture was not an object");
		const toolInput = { path: "slopgate.toml", content: "blocked" };
		const payload = { ...fixture, cwd: import.meta.dir, input: toolInput, tool_input: toolInput };

		// When
		const output = await runRealHandle(payload);

		// Then
		expect(output).toMatchObject({ block: true });
		expect(output.reason).toBeString();
	}, 30000);

	test("real cmd_handle returns a synthetic allow rewrite through the OMP CLI seam", async () => {
		// Given
		const fixturePath = path.resolve(import.meta.dir, "../../fixtures/omp/18.0.5/tool-call-bash.json");
		const fixture: unknown = JSON.parse(await Bun.file(fixturePath).text());
		if (!isRecord(fixture)) throw new HandleHarnessStateError("bash fixture was not an object");
		const pythonPath = path.join(requireTemporaryRoot(), "synthetic-engine");
		await mkdir(pythonPath, { recursive: true });
		await Bun.write(path.join(pythonPath, "sitecustomize.py"), `
import slopgate.engine
from slopgate.models import EngineResult

def synthetic_evaluate(_payload, platform="unknown"):
    return EngineResult(event_name="PreToolUse", output={"updated_input": {"command": "printf rewritten"}})

slopgate.engine.evaluate_payload = synthetic_evaluate
`);

		// When
		const output = await runRealHandle(fixture, { PYTHONPATH: pythonPath });

		// Then
		expect(output).toEqual({ updated_input: { command: "printf rewritten" } });
	}, 30000);

	test("forwards STOP-001 response bytes and schedules exactly one model continuation", async () => {
		// Given
		const activeHarness = requireHarness();
		const stopResponse = "This is pre-existing and not my change";

		// When
		const continuation = await emitStop(activeHarness, {
			lastMessage: assistantTextMessage(stopResponse),
		});
		const payload = await readRecordedPayload(requireRecordPath());
		const ruleIds = await readRuleIds(requireTemporaryRoot());
		const continuationContext = continuation?.additionalContext ?? "";
		await activeHarness.invokeModel("hidden continuation", [continuationContext]);
		const settled = await emitStop(activeHarness, {
			active: true,
			lastMessage: assistantTextMessage(stopResponse),
		});

		// Then
		expect(payload.stop_response).toBe(stopResponse);
		expect(ruleIds).toContain("STOP-001");
		expect(continuation).toMatchObject({ continue: true });
		expect(continuationContext.length).toBeGreaterThan(0);
		expect(activeHarness.model.systemPrompts.at(-1)).toContain(continuationContext);
		expect(settled).toBeUndefined();
	}, 30000);

	test("displays one STOP-002 reminder without continuing the fresh session", async () => {
		// Given
		const activeHarness = requireHarness();
		const before = activeHarness.sentMessages.length;
		const response = assistantTextMessage("Implemented the requested change and verified it.");

		// When
		const result = await emitStop(activeHarness, { lastMessage: response });
		const ruleIds = await readRuleIds(requireTemporaryRoot());
		const settled = await emitStop(activeHarness, { active: true, lastMessage: response });
		const displayed = activeHarness.sentMessages.slice(before);

		// Then
		expect(result).toBeUndefined();
		expect(ruleIds).toContain("STOP-002");
		expect(settled).toBeUndefined();
		expect(displayed).toHaveLength(1);
		expect(displayed[0]).toContain("slopgate lint check");
	}, 30000);
});
