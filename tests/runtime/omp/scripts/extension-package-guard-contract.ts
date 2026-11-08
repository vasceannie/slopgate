import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import { mkdir, mkdtemp, readFile, rm, symlink, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import * as path from "node:path";
import { pathToFileURL } from "node:url";

import { createRuntimeHarness, type RuntimeHarness } from "./runtime-harness.ts";
import {
	clearRuntimeEnvironment,
	configureFakeResponse,
	configureRuntimeEnvironment,
	createRecordPath,
	createTemporaryRoot,
	FIXED_SESSION_ID,
	readRecordedPayload,
	WORKSPACE_ROOT,
} from "./runtime-test-support.ts";

const STAGED_TEMPLATE = path.join(WORKSPACE_ROOT, "staged/omp_extension.ts");
const REPOSITORY_ROOT = path.resolve(WORKSPACE_ROOT, "../../..");
const LOADED_PACKAGE_FILES = ["index.ts", "package.json"] as const;
const MANAGED_SCOPES = ["managed", "unmanaged"] as const;
type PackageAlias =
	| "canonical"
	| "relative"
	| "tilde"
	| "at"
	| "file-url"
	| "colon-absolute"
	| "colon-relative"
	| "symlink-parent"
	| "symlink-leaf"
	| "missing-descendant"
	| "drive-alias"
	| "mnt-drive-alias";

const PACKAGE_ALIASES: readonly PackageAlias[] = [
	"canonical",
	"relative",
	"tilde",
	"at",
	"file-url",
	"colon-absolute",
	"colon-relative",
	"symlink-parent",
	"symlink-leaf",
	"missing-descendant",
	...(process.platform === "win32" ? ["drive-alias", "mnt-drive-alias"] as const : []),
];

type ManagedScope = (typeof MANAGED_SCOPES)[number];
type PackageFile = (typeof LOADED_PACKAGE_FILES)[number];
type AliasLeafPaths = ReadonlyMap<PackageFile, string>;

const PACKAGE_GUARD_CASES = MANAGED_SCOPES.flatMap((scope) =>
	PACKAGE_ALIASES.flatMap((alias) =>
		LOADED_PACKAGE_FILES.map((file) => [scope, alias, file] as const),
	),
);
const PASS_THROUGH_TARGETS = [
	["ordinary", "write"],
	["sibling-prefix", "write"],
	["literal-at", "write"],
	["internal-url", "write"],
	["malformed-file-url", "write"],
	["package-read", "read"],
] as const;
const PASS_THROUGH_CASES = MANAGED_SCOPES.flatMap((scope) =>
	PASS_THROUGH_TARGETS.map(([targetName, toolName]) => [scope, targetName, toolName] as const),
);


class GuardHarnessStateError extends Error {
	constructor() {
		super("Loaded-package guard harness is unavailable");
		this.name = "GuardHarnessStateError";
	}
}

type GuardFixture = {
	readonly managedHarness: RuntimeHarness;
	readonly unmanagedHarness: RuntimeHarness;
	readonly packageDir: string;
	readonly recordRoot: string;
	readonly recordPath: string;
	readonly symlinkParent: string;
	readonly siblingDir: string;
	readonly symlinkLeaves: AliasLeafPaths;
};

async function stageLoadedPackage(): Promise<string> {
	const packageDir = await mkdtemp(path.join(WORKSPACE_ROOT, ".loaded-package-"));
	let complete = false;
	try {
		await writeFile(path.join(packageDir, "index.ts"), await readFile(STAGED_TEMPLATE, "utf8"), "utf8");
		await writeFile(path.join(packageDir, "package.json"), JSON.stringify({ name: "omp-slopgate", type: "module" }), "utf8");
		complete = true;
		return packageDir;
	} finally {
		if (!complete) await rm(packageDir, { recursive: true, force: true });
	}
}


function harnessFor(scope: ManagedScope, fixture: GuardFixture): RuntimeHarness {
	return scope === "managed" ? fixture.managedHarness : fixture.unmanagedHarness;
}

function windowsDriveAlias(target: string, mounted: boolean): string {
	const match = /^([A-Za-z]):[\\/](.*)$/.exec(target);
	if (match === null) throw new GuardHarnessStateError();
	const drive = (match[1] ?? "").toLowerCase();
	const suffix = (match[2] ?? "").replace(/\\/g, "/");
	return `${mounted ? "/mnt/" : "/"}${drive}/${suffix}`;
}

function targetForAlias(
	alias: PackageAlias,
	file: PackageFile,
	cwd: string,
	fixture: GuardFixture,
): string {
	const canonical = path.join(fixture.packageDir, file);
	switch (alias) {
		case "canonical":
			return canonical;
		case "relative":
			return path.relative(cwd, canonical);
		case "tilde":
			return `~/${path.relative(homedir(), canonical).split(path.sep).join("/")}`;
		case "at":
			return `@${canonical}`;
		case "file-url":
			return pathToFileURL(canonical).href;
		case "colon-absolute":
			return `:${canonical}`;
		case "colon-relative": {
			const relativeTarget = path.relative(cwd, canonical);
			return relativeTarget === ".." || relativeTarget.startsWith(`..${path.sep}`)
				? `:${relativeTarget}`
				: `:./${relativeTarget}`;
		}
		case "symlink-parent":
			return path.join(fixture.symlinkParent, file);
		case "symlink-leaf": {
			const target = fixture.symlinkLeaves.get(file);
			if (target === undefined) throw new GuardHarnessStateError();
			return target;
		}
		case "missing-descendant":
			return path.join(fixture.packageDir, "nested", `${file}.missing`);
		case "drive-alias":
			return windowsDriveAlias(canonical, false);
		case "mnt-drive-alias":
			return windowsDriveAlias(canonical, true);
	}
}

function passThroughTarget(name: string, fixture: GuardFixture): string {
	switch (name) {
		case "ordinary":
			return path.join(fixture.recordRoot, "ordinary.txt");
		case "sibling-prefix":
			return path.join(fixture.siblingDir, "index.ts");
		case "literal-at":
			return "@my-file.txt";
		case "internal-url":
			return "agent://fixture/resource";
		case "malformed-file-url":
			return "file://%";
		case "package-read":
			return path.join(fixture.packageDir, "index.ts");
		default:
			throw new GuardHarnessStateError();
	}
}

export function registerExtensionPackageGuardContractTests(): void {
	describe("staged OMP loaded-package guard contract", () => {
		let fixture: GuardFixture | undefined;
		let packageDir: string | undefined;
		let recordRoot: string | undefined;
		let managedHarness: RuntimeHarness | undefined;
		let unmanagedHarness: RuntimeHarness | undefined;
		let siblingDir: string | undefined;
		let homeSnapshot: string | undefined;
		let userProfileSnapshot: string | undefined;

		function requireFixture(): GuardFixture {
			if (fixture === undefined) throw new GuardHarnessStateError();
			return fixture;
		}

		beforeAll(async () => {
			homeSnapshot = process.env.HOME;
			userProfileSnapshot = process.env.USERPROFILE;
			process.env.HOME = WORKSPACE_ROOT;
			process.env.USERPROFILE = WORKSPACE_ROOT;
			configureRuntimeEnvironment();
			const currentRecordRoot = await createTemporaryRoot("slopgate-omp-package-guard-");
			recordRoot = currentRecordRoot;
			const recordPath = await createRecordPath(currentRecordRoot, "guard");
			const currentPackageDir = await stageLoadedPackage();
			packageDir = currentPackageDir;
			const currentSiblingDir = `${currentPackageDir}-sibling`;
			siblingDir = currentSiblingDir;
			await mkdir(currentSiblingDir, { recursive: true });
			await writeFile(path.join(currentSiblingDir, "index.ts"), "sibling package");
			const symlinkParent = path.join(currentRecordRoot, "package-parent-link");
			if (process.platform === "win32") await symlink(currentPackageDir, symlinkParent, "junction");
			else await symlink(currentPackageDir, symlinkParent);
			const symlinkLeaves = new Map<PackageFile, string>();
			for (const file of LOADED_PACKAGE_FILES) {
				const link = path.join(currentRecordRoot, `${file}.leaf-link`);
				await symlink(path.join(currentPackageDir, file), link);
				symlinkLeaves.set(file, link);
			}
			const currentManagedHarness = await createRuntimeHarness({
				cwd: REPOSITORY_ROOT,
				extensionModulePath: path.join(currentPackageDir, "index.ts"),
			});
			managedHarness = currentManagedHarness;
			const currentUnmanagedHarness = await createRuntimeHarness({
				cwd: currentRecordRoot,
				extensionModulePath: path.join(currentPackageDir, "index.ts"),
			});
			unmanagedHarness = currentUnmanagedHarness;
			fixture = {
				managedHarness: currentManagedHarness,
				unmanagedHarness: currentUnmanagedHarness,
				packageDir: currentPackageDir,
				recordRoot: currentRecordRoot,
				recordPath,
				symlinkParent,
				siblingDir: currentSiblingDir,
				symlinkLeaves,
			};
		});

		afterAll(async () => {
			const closing = [managedHarness, unmanagedHarness]
				.filter((harness): harness is RuntimeHarness => harness !== undefined)
				.map((harness) => harness.close());
			try {
				const outcomes = await Promise.allSettled(closing);
				const failure = outcomes.find((outcome) => outcome.status === "rejected");
				if (failure?.status === "rejected") throw failure.reason;
			} finally {
				clearRuntimeEnvironment();
				if (homeSnapshot === undefined) delete process.env.HOME;
				else process.env.HOME = homeSnapshot;
				if (userProfileSnapshot === undefined) delete process.env.USERPROFILE;
				else process.env.USERPROFILE = userProfileSnapshot;
				const ownedRoots = [packageDir, recordRoot, siblingDir]
					.filter((root): root is string => root !== undefined);
				await Promise.all(ownedRoots.map((root) => rm(root, { recursive: true, force: true })));
			}
		});

		test.each(PACKAGE_GUARD_CASES)(
			"blocks writes and native edits from %s cwd through %s alias for %s",
			async (scope, alias, file) => {
				const current = requireFixture();
				const harness = harnessFor(scope, current);
				const cwd = scope === "managed" ? REPOSITORY_ROOT : current.recordRoot;
				const target = targetForAlias(alias, file, cwd, current);
				const writeResult = await harness.runner.emitToolCall({
					type: "tool_call",
					toolCallId: `package-write-${scope}-${alias}-${file}`,
					toolName: "write",
					input: { path: target, content: "tampered" },
				});
				expect(writeResult?.block, "host-equivalent package writes are refused").toBe(true);
				expect(writeResult?.reason, "the refusal attributes the original target").toContain(target);

				const hashlineResult = await harness.runner.emitToolCall({
					type: "tool_call",
					toolCallId: `package-hashline-${scope}-${alias}-${file}`,
					toolName: "edit",
					input: { input: `[${target}#a1b2]\n+tampered` },
				});
				expect(hashlineResult?.block, "host-equivalent hashline edits are refused").toBe(true);
				expect(hashlineResult?.reason, "the hashline refusal attributes the original target").toContain(target);

				const patchResult = await harness.runner.emitToolCall({
					type: "tool_call",
					toolCallId: `package-patch-${scope}-${alias}-${file}`,
					toolName: "edit",
					input: { input: `*** Begin Patch\n*** Update File: ${target}\n@@\n-a\n+b\n*** End Patch` },
				});
				expect(patchResult?.block, "host-equivalent patch edits are refused").toBe(true);
				expect(patchResult?.reason, "the patch refusal attributes the original target").toContain(target);
			},
			30000,
		);

		test.each(PASS_THROUGH_CASES)(
			"does not deny %s cwd target %s via %s",
			async (scope, targetName, toolName) => {
				const current = requireFixture();
				const harness = harnessFor(scope, current);
				const target = passThroughTarget(targetName, current);
				const toolCallId = `package-pass-through-${scope}-${targetName}`;
				configureFakeResponse({});
				process.env.SLOPGATE_FAKE_RECORD_PATH = current.recordPath;
				const result = await harness.runner.emitToolCall({
					type: "tool_call",
					toolCallId,
					toolName,
					input: { path: target, content: "unchanged" },
				});
				expect(result?.block, `${targetName} is not denied by package containment`).not.toBe(true);
				const forwarded = await readRecordedPayload(current.recordPath);
				expect(forwarded.tool_call_id, `${targetName} reaches the enforcer`).toBe(toolCallId);
			},
			30000,
		);

		test.each(MANAGED_SCOPES)(
			"keeps slopgate.toml repo-gated from %s cwd",
			async (scope) => {
				const current = requireFixture();
				const harness = harnessFor(scope, current);
				configureFakeResponse({});
				process.env.SLOPGATE_FAKE_RECORD_PATH = current.recordPath;
				const toolCallId = `package-config-${scope}`;
				const result = await harness.runner.emitToolCall({
					type: "tool_call",
					toolCallId,
					toolName: "write",
					input: { path: "slopgate.toml", content: "" },
				});
				if (scope === "managed") {
					expect(result?.block, "managed repositories retain local infrastructure protection").toBe(true);
					expect(result?.reason, "the managed refusal attributes slopgate.toml").toContain("slopgate.toml");
				} else {
					expect(result?.block, "unmanaged cwd does not acquire repo-local protection").not.toBe(true);
					const forwarded = await readRecordedPayload(current.recordPath);
					expect(forwarded.tool_call_id, "unmanaged slopgate.toml writes reach the enforcer").toBe(toolCallId);
				}
			},
			30000,
		);

		test("ordinary reads remain pass-through and retain session identity", async () => {
			const current = requireFixture();
			configureFakeResponse({});
			process.env.SLOPGATE_FAKE_RECORD_PATH = current.recordPath;
			const ordinaryRead = await current.managedHarness.runner.emitToolCall({
				type: "tool_call",
				toolCallId: "loaded-package-read-session",
				toolName: "read",
				input: { path: "README.md" },
			});
			const forwarded = await readRecordedPayload(current.recordPath);
			expect(ordinaryRead?.block, "ordinary reads are never blocked by mutation guards").not.toBe(true);
			expect(
				{ tool: forwarded.tool_call_id, session: forwarded.session_id },
				"ordinary reads reach the enforcer with the session identity",
			).toEqual({ tool: "loaded-package-read-session", session: FIXED_SESSION_ID });
		}, 30000);
	});
}
