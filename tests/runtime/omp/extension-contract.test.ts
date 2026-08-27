import { afterEach, describe, expect, test } from "bun:test";
import { existsSync } from "node:fs";
import { mkdtemp, readdir, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { registerExtensionLifecycleContractTests } from "./scripts/extension-lifecycle-contract.ts";
import { registerExtensionToolContractTests } from "./scripts/extension-tool-contract.ts";
import { assertCaptureDirectoriesEqual, captureEnvelopes } from "./scripts/envelope-capture.ts";

const EXPECTED_SCRIPTS = {
	test: "bun test scripts/verify-snapshot.test.ts extension-contract.test.ts discovery-contract.test.ts handle-integration.test.ts",
	stage: "bun run scripts/stage-template.ts",
	pretest: "bun run stage",
	typecheck:
		"bun run stage && tsc --noEmit --target ES2022 --module ESNext --moduleResolution Bundler --strict --skipLibCheck --types node --verbatimModuleSyntax staged/omp_extension.ts",
	capture: "bun run stage && bun run capture-contract.ts",
	"verify:package": "bun run scripts/verify-package.ts",
	"verify:system": "uv run python scripts/verify-real-system.py",
} as const;

const EXPECTED_CAPTURE_FILES = [
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

type PackageManifest = {
	readonly scripts?: Readonly<Record<string, unknown>>;
};

const temporaryPaths: string[] = [];

afterEach(async () => {
	await Promise.all(temporaryPaths.splice(0).map(temporaryPath => rm(temporaryPath, { recursive: true, force: true })));
});

function isPackageManifest(value: unknown): value is PackageManifest {
	return typeof value === "object" && value !== null;
}

async function runWorkspaceCommand(command: string[]): Promise<{
	readonly exitCode: number;
	readonly stderr: string;
}> {
	const process = Bun.spawn(command, {
		cwd: import.meta.dir,
		stdout: "ignore",
		stderr: "pipe",
	});
	const [exitCode, stderr] = await Promise.all([process.exited, new Response(process.stderr).text()]);
	return { exitCode, stderr };
}

describe("Todo 6 workspace contract", () => {
	test("uses the exact final package scripts", async () => {
		// Given
		const raw = await Bun.file(new URL("package.json", import.meta.url)).text();
		const parsed: unknown = JSON.parse(raw);

		// When
		const scripts = isPackageManifest(parsed) ? parsed.scripts : undefined;

		// Then
		expect(scripts).toMatchObject(EXPECTED_SCRIPTS);
		expect(raw.includes('test.ts""')).toBe(false);
	});

	test("stages the production renderer deterministically with only the placeholder substituted", async () => {
		// Given
		const sourcePath = path.resolve(import.meta.dir, "../../../src/slopgate/resources/omp_extension.ts");
		const stagedPath = path.join(import.meta.dir, "staged/omp_extension.ts");
		const source = await Bun.file(sourcePath).text();

		// When
		const firstRun = await runWorkspaceCommand(["bun", "scripts/stage-template.ts"]);
		const first = await Bun.file(stagedPath).text();
		const secondRun = await runWorkspaceCommand(["bun", "scripts/stage-template.ts"]);
		const second = await Bun.file(stagedPath).text();

		// Then
		expect(firstRun).toEqual({ exitCode: 0, stderr: "" });
		expect(secondRun).toEqual({ exitCode: 0, stderr: "" });
		expect(second).toBe(first);
		expect(first).not.toContain("__SLOPGATE_ARGV__");
		expect(first.replace('["python3"]', '["__SLOPGATE_BIN__"]')).toBe(source);
	}, 30000);

	test("fake enforcer records stdin bytes and returns a canned response", async () => {
		// Given
		const temporaryRoot = await mkdtemp(path.join(tmpdir(), "slopgate-omp-enforcer-"));
		temporaryPaths.push(temporaryRoot);
		const recordPath = path.join(temporaryRoot, "stdin.json");
		const executable = path.join(import.meta.dir, "fake-enforcer/slopgate");
		const stdin = '{"event_name":"PreToolUse","tool_name":"Bash"}';
		const response = '{"block":true,"reason":"blocked by fixture"}';

		// When
		const child = Bun.spawn([executable, "handle", "--platform", "omp"], {
			cwd: import.meta.dir,
			env: {
				...process.env,
				SLOPGATE_FAKE_RECORD_PATH: recordPath,
				SLOPGATE_FAKE_RESPONSE: response,
			},
			stdin: new Blob([stdin]),
			stdout: "pipe",
			stderr: "pipe",
		});
		const [exitCode, stdout, stderr] = await Promise.all([
			child.exited,
			new Response(child.stdout).text(),
			new Response(child.stderr).text(),
		]);

		// Then
		expect({ exitCode, stdout, stderr }).toEqual({ exitCode: 0, stdout: response, stderr: "" });
		expect(await Bun.file(recordPath).text()).toBe(stdin);
	}, 30000);

	test("produces byte-identical envelopes across two consecutive captures", async () => {
		// Given
		const first = await mkdtemp(path.join(tmpdir(), "slopgate-omp-capture-first-"));
		const second = await mkdtemp(path.join(tmpdir(), "slopgate-omp-capture-second-"));
		temporaryPaths.push(first, second);

		// When
		await captureEnvelopes(first);
		await captureEnvelopes(second);

		// Then
		await expect(assertCaptureDirectoriesEqual(first, second)).resolves.toBeUndefined();
	}, 60000);

	test("commits the exact envelope set without creating capture scratch state", async () => {
		// Given
		const fixtureRoot = path.resolve(import.meta.dir, "../../fixtures/omp");
		const versionRoot = path.join(fixtureRoot, "18.0.5");

		// When
		const files = (await readdir(versionRoot)).toSorted();

		// Then
		expect(files).toEqual([...EXPECTED_CAPTURE_FILES]);
		expect(existsSync(path.join(fixtureRoot, ".capture"))).toBe(false);
	});
});

registerExtensionToolContractTests();
registerExtensionLifecycleContractTests();
