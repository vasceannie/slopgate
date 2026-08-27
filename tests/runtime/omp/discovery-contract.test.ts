import { afterEach, describe, expect, test } from "bun:test";
import { mkdir, mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import * as path from "node:path";

type CommandResult = {
	readonly exitCode: number;
	readonly stdout: string;
	readonly stderr: string;
};

type DiscoveryResult = {
	readonly items: readonly unknown[];
	readonly providers: readonly unknown[];
	readonly warnings: readonly unknown[];
};

const REPO_ROOT = path.resolve(import.meta.dir, "../../..");
const SANITIZED_KEYS = [
	"SLOPGATE_CONFIG",
	"SLOPGATE_CONFIG_DIR",
	"SLOPGATE_ROOT",
	"CLAUDE_HOOK_LAYER_ROOT",
	"HOOK_LAYER_ROOT",
] as const;
const temporaryPaths: string[] = [];

function containedBy(root: string, candidate: string): boolean {
	const relative = path.relative(root, candidate);
	return relative === "" || (!relative.startsWith("..") && !path.isAbsolute(relative));
}

function isolatedEnvironment(root: string, agentDir: string | undefined): NodeJS.ProcessEnv {
	const environment: NodeJS.ProcessEnv = {
		...process.env,
		HOME: path.join(root, "home"),
		XDG_CONFIG_HOME: path.join(root, "xdg-config"),
		XDG_DATA_HOME: path.join(root, "xdg-data"),
		XDG_STATE_HOME: path.join(root, "xdg-state"),
	};
	for (const key of SANITIZED_KEYS) delete environment[key];
	if (agentDir === undefined) {
		delete environment.PI_CODING_AGENT_DIR;
	} else {
		environment.PI_CODING_AGENT_DIR = agentDir;
	}
	delete environment.OMP_AGENT_DIR;
	return environment;
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

function parseDiscovery(stdout: string): DiscoveryResult {
	const parsed: unknown = JSON.parse(stdout);
	if (typeof parsed !== "object" || parsed === null) {
		return { items: [], providers: [], warnings: [] };
	}
	return {
		items: "items" in parsed && Array.isArray(parsed.items) ? parsed.items : [],
		providers: "providers" in parsed && Array.isArray(parsed.providers) ? parsed.providers : [],
		warnings: "warnings" in parsed && Array.isArray(parsed.warnings) ? parsed.warnings : [],
	};
}

afterEach(async () => {
	await Promise.all(temporaryPaths.splice(0).map(root => rm(root, { recursive: true, force: true })));
});

describe("installer-driven OMP discovery", () => {
	test.each([
		["default agent directory", false],
		["absolute PI_CODING_AGENT_DIR", true],
	] as const)("installs user and project sites and discovers one extension with %s", async (_name, useOverride) => {
		// Given
		const isolatedRoot = await mkdtemp(path.join(tmpdir(), "slopgate-omp-discovery-"));
		temporaryPaths.push(isolatedRoot);
		const projectRoot = path.join(isolatedRoot, "project");
		const overrideAgentDir = useOverride ? path.join(isolatedRoot, "profiles", "omp-agent") : undefined;
		const env = isolatedEnvironment(isolatedRoot, overrideAgentDir);
		const userAgentDir = overrideAgentDir ?? path.join(isolatedRoot, "home", ".omp", "agent");
		await mkdir(projectRoot, { recursive: true });
		const mutationRoots = [
			projectRoot,
			userAgentDir,
			env.XDG_CONFIG_HOME,
			env.XDG_DATA_HOME,
			env.XDG_STATE_HOME,
		];
		for (const candidate of mutationRoots) {
			expect(typeof candidate === "string" && containedBy(isolatedRoot, candidate)).toBe(true);
		}

		// When
		const install = await run(
			[
				"uv",
				"run",
				"slopgate",
				"install",
				"omp",
				"--disable-autoupdate",
				"--install-scope",
				"both",
				"--project-root",
				projectRoot,
			],
			REPO_ROOT,
			env,
		);
		const discovery = await run(
			["bun", "run", "scripts/discover-installed.ts", projectRoot],
			import.meta.dir,
			env,
		);

		// Then
		expect(install).toMatchObject({ exitCode: 0, stderr: "" });
		expect(discovery).toMatchObject({ exitCode: 0, stderr: "" });
		const result = parseDiscovery(discovery.stdout);
		expect(await Bun.file(path.join(userAgentDir, "extensions/omp-slopgate/index.ts")).exists()).toBe(true);
		expect(await Bun.file(path.join(projectRoot, ".omp/extensions/omp-slopgate/index.ts")).exists()).toBe(true);
		expect(result.warnings).toEqual([]);
		expect(result.items).toHaveLength(1);
		expect(result.items[0]).toMatchObject({ name: "omp-slopgate", level: "project" });
		expect(result.providers).toEqual(["native"]);
	}, 30000);
});
