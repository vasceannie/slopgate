import { afterEach, describe, expect, test } from "bun:test";
import { cp, mkdir, mkdtemp, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import * as path from "node:path";

type CommandResult = {
	readonly exitCode: number;
	readonly stdout: string;
	readonly stderr: string;
};

type OmpRegistration = {
	readonly scope: string;
	readonly version: string;
	readonly installPath: string;
	readonly enabled?: boolean;
};

const REPOSITORY_ROOT = path.resolve(import.meta.dir, "../../..");
const OMP_PLUGIN_ID = "omp-slopgate@slopgate-runtime";
const REQUIRED_SCOPES = ["project", "user"];
const temporaryPaths: string[] = [];

function containedBy(root: string, candidate: string): boolean {
	const relative = path.relative(root, candidate);
	return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
}

function isolatedEnvironment(root: string, agentDir: string | undefined): NodeJS.ProcessEnv {
	const home = path.join(root, "home");
	const environment: NodeJS.ProcessEnv = {
		PATH: process.env.PATH,
		HOME: home,
		USERPROFILE: home,
		XDG_CONFIG_HOME: path.join(root, "xdg-config"),
		XDG_DATA_HOME: path.join(root, "xdg-data"),
		XDG_STATE_HOME: path.join(root, "xdg-state"),
		XDG_CACHE_HOME: path.join(root, "xdg-cache"),
		XDG_RUNTIME_DIR: root,
		CLAUDE_CONFIG_DIR: path.join(home, ".claude"),
		SLOPGATE_CONFIG_DIR: path.join(root, "slopgate-config"),
		SLOPGATE_ROOT: path.join(root, "slopgate-state"),
		SLOPGATE_LOG_DIR: path.join(root, "slopgate-log"),
		SLOPGATE_DAEMON_SOCKET: path.join(root, "slopgate-state", "unused.sock"),
		TMPDIR: root,
		TEMP: root,
		TMP: root,
		TERM: "dumb",
		NO_COLOR: "1",
		LANG: "C.UTF-8",
	};
	if (process.platform === "win32") {
		environment.APPDATA = path.join(root, "appdata");
		environment.LOCALAPPDATA = path.join(root, "localappdata");
		environment.SYSTEMROOT = process.env.SYSTEMROOT;
		environment.COMSPEC = process.env.COMSPEC;
	}
	if (agentDir !== undefined) environment.PI_CODING_AGENT_DIR = agentDir;
	return environment;
}

async function linkRuntimePeers(sandboxRoot: string): Promise<void> {
	const scope = path.join(sandboxRoot, "node_modules", "@oh-my-pi");
	const workspace = path.join(REPOSITORY_ROOT, "tests", "runtime", "omp", "node_modules", "@oh-my-pi");
	const peers = ["pi-coding-agent", "pi-tui"] as const;
	await mkdir(scope, { recursive: true });
	await Promise.all(peers.map(async (name) => {
		const source = path.join(workspace, name);
		const target = path.join(scope, name);
		if (process.platform === "win32") {
			await cp(source, target, { recursive: true });
		} else {
			await symlink(source, target, "dir");
		}
	}));
}

async function seedEnrolledProject(projectRoot: string): Promise<void> {
	await Promise.all([
		writeFile(path.join(projectRoot, "slopgate.toml"), "[slopgate]\nenabled = true\n", "utf8"),
		writeFile(path.join(projectRoot, "README.md"), "Native OMP runtime project.\n", "utf8"),
	]);
}

async function run(command: string[], cwd: string, env: NodeJS.ProcessEnv): Promise<CommandResult> {
	const child = Bun.spawn(command, { cwd, env, stdout: "pipe", stderr: "pipe" });
	const [exitCode, stdout, stderr] = await Promise.all([
		child.exited,
		new Response(child.stdout).text(),
		new Response(child.stderr).text(),
	]);
	return { exitCode, stdout, stderr };
}


function parseObject(stdout: string, label: string): Record<string, unknown> {
	const parsed: unknown = JSON.parse(stdout);
	if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
		throw new Error(`${label} did not return a JSON object`);
	}
	return parsed as Record<string, unknown>;
}

function parseNativeRegistrations(stdout: string): OmpRegistration[] {
	const inventory = parseObject(stdout, "omp plugin list --json");
	const marketplaces = inventory.marketplace;
	if (!Array.isArray(marketplaces)) {
		throw new Error("OMP native inventory has no marketplace array");
	}
	const registrations: OmpRegistration[] = [];
	for (const rawMarketplace of marketplaces) {
		if (typeof rawMarketplace !== "object" || rawMarketplace === null || Array.isArray(rawMarketplace)) {
			throw new Error("OMP native inventory contains a malformed marketplace");
		}
		const marketplace = rawMarketplace as Record<string, unknown>;
		if (marketplace.id !== OMP_PLUGIN_ID) continue;
		const entries = marketplace.entries;
		if (!Array.isArray(entries)) throw new Error("OMP Slopgate registration has no entries");
		for (const rawEntry of entries) {
			if (typeof rawEntry !== "object" || rawEntry === null || Array.isArray(rawEntry)) {
				throw new Error("OMP Slopgate entry is malformed");
			}
			const entry = rawEntry as Record<string, unknown>;
			const { scope, version, installPath, enabled } = entry;
			if (
				typeof scope !== "string" ||
				typeof version !== "string" ||
				typeof installPath !== "string" ||
				(enabled !== undefined && typeof enabled !== "boolean")
			) {
				throw new Error(`OMP Slopgate entry has invalid fields: ${JSON.stringify(entry)}`);
			}
			registrations.push({
				scope,
				version,
				installPath,
				...(typeof enabled === "boolean" ? { enabled } : {}),
			});
		}
	}
	return registrations;
}

function requireRegistration(
	registrations: readonly OmpRegistration[],
	scope: string,
): OmpRegistration {
	const matches = registrations.filter((entry) => entry.scope === scope);
	const registration = matches[0];
	if (matches.length !== 1 || registration === undefined) {
		throw new Error(`Expected one native OMP registration for ${scope}, got ${matches.length}`);
	}
	return registration;
}

afterEach(async () => {
	await Promise.all(temporaryPaths.splice(0).map((root) => rm(root, { recursive: true, force: true })));
});

describe("installer-driven OMP native registration", () => {
	test.each([
		["default agent directory", false],
		["absolute PI_CODING_AGENT_DIR", true],
	] as const)("registers and loads the native package with %s", async (_name, useOverride) => {
		const isolatedRoot = await mkdtemp(path.join(tmpdir(), "slopgate-omp-discovery-"));
		temporaryPaths.push(isolatedRoot);
		const projectRoot = path.join(isolatedRoot, "project");
		const overrideAgentDir = useOverride
			? path.join(isolatedRoot, "profiles", "omp-agent")
			: undefined;
		const env = isolatedEnvironment(isolatedRoot, overrideAgentDir);
		const userAgentDir = overrideAgentDir ?? path.join(isolatedRoot, "home", ".omp", "agent");
		const mutationRoots = [
			projectRoot,
			userAgentDir,
			env.XDG_CONFIG_HOME,
			env.XDG_DATA_HOME,
			env.XDG_STATE_HOME,
			env.XDG_CACHE_HOME,
			env.SLOPGATE_CONFIG_DIR,
			env.SLOPGATE_ROOT,
			env.SLOPGATE_LOG_DIR,
		];
		expect(mutationRoots.every(
			(candidate) => typeof candidate === "string" && containedBy(isolatedRoot, candidate),
		)).toBe(true);
		await Promise.all([
			mkdir(projectRoot, { recursive: true }),
			mkdir(userAgentDir, { recursive: true }),
			mkdir(env.XDG_CONFIG_HOME!, { recursive: true }),
			mkdir(env.XDG_DATA_HOME!, { recursive: true }),
			mkdir(env.XDG_STATE_HOME!, { recursive: true }),
			mkdir(env.XDG_CACHE_HOME!, { recursive: true }),
			mkdir(env.SLOPGATE_CONFIG_DIR!, { recursive: true }),
			mkdir(env.SLOPGATE_ROOT!, { recursive: true }),
			mkdir(env.SLOPGATE_LOG_DIR!, { recursive: true }),
		]);
		await seedEnrolledProject(projectRoot);
		await linkRuntimePeers(isolatedRoot);

		const slopgateBinary = path.join(
			REPOSITORY_ROOT,
			".venv",
			process.platform === "win32" ? "Scripts/slopgate.exe" : "bin/slopgate",
		);
		const install = await run(
			[
				slopgateBinary,
				"install",
				"omp",
				"--disable-autoupdate",
				"--install-scope",
				"both",
				"--project-root",
				projectRoot,
			],
			REPOSITORY_ROOT,
			env,
		);
		expect(install.exitCode).toBe(0);
		expect(install.stdout).toContain(OMP_PLUGIN_ID);

		const inventory = await run(["omp", "plugin", "list", "--json"], projectRoot, env);
		expect(inventory.exitCode).toBe(0);
		const registrations = parseNativeRegistrations(inventory.stdout);
		expect(registrations.map((entry) => entry.scope).sort()).toEqual(REQUIRED_SCOPES);
		const projectRegistration = requireRegistration(registrations, "project");
		const userRegistration = requireRegistration(registrations, "user");
		expect([projectRegistration, userRegistration].every((entry) => entry.enabled !== false)).toBe(true);
		expect([projectRegistration, userRegistration].every(
			(entry) => path.isAbsolute(entry.installPath) && containedBy(isolatedRoot, entry.installPath),
		)).toBe(true);
		const registeredIndex = path.join(projectRegistration.installPath, "index.ts");
		expect(await Bun.file(registeredIndex).exists()).toBe(true);
		expect(await Bun.file(path.join(projectRegistration.installPath, "package.json")).exists()).toBe(true);

		const legacyPaths = [
			path.join(userAgentDir, "extensions", "omp-slopgate", "index.ts"),
			path.join(projectRoot, ".omp", "extensions", "omp-slopgate", "index.ts"),
		];
		expect(await Promise.all(legacyPaths.map((legacyPath) => Bun.file(legacyPath).exists())))
			.toEqual([false, false]);

		const recordPath = path.join(isolatedRoot, "records", "omp-runtime.json");
		await mkdir(path.dirname(recordPath), { recursive: true });
		const runtime = await run(
			["bun", "run", "scripts/load-installed.ts", registeredIndex, projectRoot, recordPath],
			import.meta.dir,
			env,
		);
		expect(runtime).toMatchObject({ exitCode: 0 });
		const evidence = parseObject(runtime.stdout, "registered OMP ExtensionRunner");
		expect(evidence).toMatchObject({
			loaded: true,
			extensions: 1,
			blocked: {
				write: expect.stringContaining("slopgate.toml"),
				hashline: expect.stringContaining("slopgate.toml"),
				applyPatch: expect.stringContaining("slopgate.toml"),
			},
		});
		expect(evidence.packageWrites).toMatchObject({
			index: {
				blocked: true,
				reason: expect.stringMatching(/^Cannot modify Slopgate infrastructure: .+/),
			},
			manifest: {
				blocked: true,
				reason: expect.stringMatching(/^Cannot modify Slopgate infrastructure: .+/),
			},
		});
		expect(evidence.session).toEqual(expect.any(String));
	}, 30000);
});
