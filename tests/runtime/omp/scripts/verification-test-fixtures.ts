import { spawnSync } from "node:child_process";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

import {
  ContractLockError,
  WORKSPACE_ROOT,
  type ContractSnapshot,
  type ListenerContract,
} from "./snapshot-schema.ts";

export type VerifyMode = "adapter" | "all" | "bridge";

export type VerifierRun = {
  readonly exitCode: number;
  readonly stderr: string;
};

type SyntheticFiles = {
  readonly adapterSource?: string;
  readonly bridgeSource?: string;
  readonly constantsSource?: string;
};

type BridgeOverride = {
  readonly body: string;
  readonly event: string;
  readonly prelude?: string;
};

const temporaryRoots: string[] = [];

export async function cleanupSyntheticRepos(): Promise<void> {
  await Promise.all(temporaryRoots.splice(0).map((root) => rm(root, { force: true, recursive: true })));
}

export async function createSyntheticRepo(files: SyntheticFiles): Promise<string> {
  const repoRoot = await mkdtemp(join(tmpdir(), "slopgate-omp-contract-"));
  temporaryRoots.push(repoRoot);

  if (files.adapterSource !== undefined) {
    const adapterDirectory = join(repoRoot, "src", "slopgate", "adapters");
    await mkdir(adapterDirectory, { recursive: true });
    await writeFile(join(adapterDirectory, "omp.py"), files.adapterSource, "utf8");
  }
  if (files.bridgeSource !== undefined) {
    const bridgeDirectory = join(repoRoot, "src", "slopgate", "resources");
    await mkdir(bridgeDirectory, { recursive: true });
    await writeFile(join(bridgeDirectory, "omp_extension.ts"), files.bridgeSource, "utf8");
  }
  if (files.constantsSource !== undefined) {
    const constantsDirectory = join(repoRoot, "src", "slopgate");
    await mkdir(constantsDirectory, { recursive: true });
    await writeFile(join(constantsDirectory, "constants.py"), files.constantsSource, "utf8");
  }
  return repoRoot;
}

export function runVerifier(repoRoot: string, mode: VerifyMode): VerifierRun {
  const process = spawnSync(
    "bun",
    ["run", "scripts/verify-snapshot.ts", "--repo-root", repoRoot, "--require", mode],
    { cwd: WORKSPACE_ROOT, encoding: "utf8", stdio: ["ignore", "ignore", "pipe"] },
  );
  if (process.error) throw process.error;
  return { exitCode: process.status ?? 1, stderr: process.stderr };
}

export function buildBridgeSource(
  snapshot: ContractSnapshot,
  override?: BridgeOverride,
): string {
  const registrations = Object.entries(snapshot.listeners).map(([event, contract]) => {
    const body = override?.event === event ? override.body : defaultListenerBody(contract);
    return `pi.on(${JSON.stringify(event)}, () => { ${body} });`;
  });
  const prelude = override?.prelude === undefined ? "" : `${override.prelude}\n`;
  return `${prelude}declare const pi: { on(event: string, callback: () => unknown): void };\n${registrations.join("\n")}\n`;
}

export function incompatibleFieldFor(
  snapshot: ContractSnapshot,
  target: ListenerContract,
): string {
  for (const contract of Object.values(snapshot.listeners)) {
    for (const field of Object.keys(contract.fields)) {
      if (!(field in target.fields)) return field;
    }
  }
  throw new ContractLockError("snapshot listener inventory has no incompatible field");
}

function defaultListenerBody(contract: ListenerContract): string {
  const fields = Object.keys(contract.fields);
  if (fields.length === 0) return "return;";
  return `return { ${JSON.stringify(fields[0])}: undefined };`;
}
