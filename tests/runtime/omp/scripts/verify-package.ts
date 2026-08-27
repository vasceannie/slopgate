import * as path from "node:path";

const WORKSPACE_ROOT = path.resolve(import.meta.dir, "..");

const EXPECTED_SCRIPTS = {
	lock: "bun run scripts/lock-contract.ts",
	"verify:snapshot": "bun run scripts/verify-snapshot.ts",
	test: "bun test scripts/verify-snapshot.test.ts extension-contract.test.ts discovery-contract.test.ts handle-integration.test.ts",
	stage: "bun run scripts/stage-template.ts",
	pretest: "bun run stage",
	typecheck:
		"bun run stage && tsc --noEmit --target ES2022 --module ESNext --moduleResolution Bundler --strict --skipLibCheck --types node --verbatimModuleSyntax staged/omp_extension.ts",
	capture: "bun run stage && bun run capture-contract.ts",
	"verify:package": "bun run scripts/verify-package.ts",
	"verify:system": "uv run python scripts/verify-real-system.py",
} as const;

const REQUIRED_FILES = [
	"capture-contract.ts",
	"discovery-contract.test.ts",
	"extension-contract.test.ts",
	"handle-integration.test.ts",
	"scripts/lock-contract.ts",
	"scripts/stage-template.ts",
	"scripts/verify-package.ts",
	"scripts/verify-real-system.py",
	"scripts/verify-snapshot.test.ts",
	"scripts/verify-snapshot.ts",
] as const;

const PINNED_DEV_DEPENDENCIES = {
	"@oh-my-pi/pi-coding-agent": "18.0.5",
	"@oh-my-pi/pi-tui": "18.0.5",
} as const;

class PackageContractError extends Error {
	constructor(detail: string) {
		super(`OMP package contract failed: ${detail}`);
		this.name = "PackageContractError";
	}
}

function isRecord(value: unknown): value is Readonly<Record<string, unknown>> {
	return typeof value === "object" && value !== null && !Array.isArray(value);
}

function requireRecord(value: unknown, name: string): Readonly<Record<string, unknown>> {
	if (!isRecord(value)) throw new PackageContractError(`${name} must be an object`);
	return value;
}

function assertExactStringMap(
	actual: Readonly<Record<string, unknown>>,
	expected: Readonly<Record<string, string>>,
	name: string,
): void {
	const actualKeys = Object.keys(actual).toSorted();
	const expectedKeys = Object.keys(expected).toSorted();
	if (actualKeys.length !== expectedKeys.length || actualKeys.some((key, index) => key !== expectedKeys[index])) {
		throw new PackageContractError(`${name} keys differ: ${actualKeys.join(", ")}`);
	}
	for (const [key, expectedValue] of Object.entries(expected)) {
		if (actual[key] !== expectedValue) throw new PackageContractError(`${name}.${key} differs`);
	}
}

const packagePath = path.join(WORKSPACE_ROOT, "package.json");
const rawManifest = await Bun.file(packagePath).text();
if (rawManifest.includes('test.ts""')) throw new PackageContractError('package.json contains test.ts""');

const parsed: unknown = JSON.parse(rawManifest);
const manifest = requireRecord(parsed, "package.json");
const scripts = requireRecord(manifest.scripts, "package.json scripts");
const devDependencies = requireRecord(manifest.devDependencies, "package.json devDependencies");
assertExactStringMap(scripts, EXPECTED_SCRIPTS, "scripts");

for (const [dependency, version] of Object.entries(PINNED_DEV_DEPENDENCIES)) {
	if (devDependencies[dependency] !== version) {
		throw new PackageContractError(`${dependency} must be pinned to ${version}`);
	}
}

for (const relativePath of REQUIRED_FILES) {
	if (!(await Bun.file(path.join(WORKSPACE_ROOT, relativePath)).exists())) {
		throw new PackageContractError(`missing ${relativePath}`);
	}
}

if (await Bun.file(path.join(WORKSPACE_ROOT, "tsconfig.json")).exists()) {
	throw new PackageContractError("tsconfig.json must not exist in this workspace");
}
