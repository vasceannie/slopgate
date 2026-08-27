import { resolve } from "node:path";

import { verifyAdapter } from "./adapter-verification.ts";
import { verifyBridge } from "./bridge-verification.ts";
import { ContractLockError, WORKSPACE_ROOT } from "./snapshot-schema.ts";
import { verifyLockedSnapshot } from "./snapshot-verification.ts";

type RequireMode = "adapter" | "all" | "bridge";

type CliOptions = {
  readonly repoRoot: string;
  readonly requireMode: RequireMode;
};

function parseArguments(args: readonly string[]): CliOptions {
  let repoRoot = resolve(WORKSPACE_ROOT, "../../..");
  let requireMode: RequireMode = "all";
  for (let index = 0; index < args.length; index += 1) {
    const argument = args[index];
    if (argument === "--repo-root") {
      const value = args[index + 1];
      if (!value) throw new ContractLockError("--repo-root requires a directory");
      repoRoot = resolve(value);
      index += 1;
      continue;
    }
    if (argument === "--require") {
      const value = args[index + 1];
      if (value !== "adapter" && value !== "bridge" && value !== "all") {
        throw new ContractLockError("--require must be adapter, bridge, or all");
      }
      requireMode = value;
      index += 1;
      continue;
    }
    throw new ContractLockError(`unknown argument: ${argument ?? "<missing>"}`);
  }
  return { repoRoot, requireMode };
}

async function run(): Promise<void> {
  const options = parseArguments(process.argv.slice(2));
  const snapshot = await verifyLockedSnapshot();
  if (options.requireMode === "adapter" || options.requireMode === "all") {
    verifyAdapter(options.repoRoot, snapshot);
  }
  if (options.requireMode === "bridge" || options.requireMode === "all") {
    verifyBridge(options.repoRoot, snapshot);
  }
}

async function main(): Promise<void> {
  try {
    await run();
  } catch (error: unknown) {
    if (!(error instanceof ContractLockError)) throw error;
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
  }
}

await main();
