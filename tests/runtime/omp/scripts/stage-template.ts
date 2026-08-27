import { mkdir } from "node:fs/promises";
import * as path from "node:path";

const REPO_ROOT = path.resolve(import.meta.dir, "../../../..");
const STAGED_PATH = path.join(REPO_ROOT, "tests/runtime/omp/staged/omp_extension.ts");
const RENDER_CODE = [
	"from slopgate.installer._omp import render_omp_extension",
	"from slopgate.resources import resource_path",
	'template = resource_path("omp_extension.ts").read_text(encoding="utf-8")',
	'print(render_omp_extension(template, "python3"), end="")',
].join("; ");

class RendererProcessError extends Error {
	constructor(
		readonly exitCode: number,
		readonly stderr: string,
	) {
		super(`OMP renderer exited with ${exitCode}: ${stderr.trim()}`);
		this.name = "RendererProcessError";
	}
}

async function renderTemplate(): Promise<string> {
	const process = Bun.spawn(["uv", "run", "python", "-c", RENDER_CODE], {
		cwd: REPO_ROOT,
		stdout: "pipe",
		stderr: "pipe",
	});
	const [exitCode, stdout, stderr] = await Promise.all([
		process.exited,
		new Response(process.stdout).text(),
		new Response(process.stderr).text(),
	]);
	if (exitCode !== 0) {
		throw new RendererProcessError(exitCode, stderr);
	}
	return stdout;
}

export async function stageTemplate(): Promise<void> {
	const first = await renderTemplate();
	const second = await renderTemplate();
	if (first !== second) {
		throw new Error("OMP renderer produced nondeterministic output");
	}
	await mkdir(path.dirname(STAGED_PATH), { recursive: true });
	await Bun.write(STAGED_PATH, first);
}

if (import.meta.main) {
	await stageTemplate();
}
