import { spawnSync } from "node:child_process";
import { writeFile } from "node:fs/promises";

import { ContractLockError, SNAPSHOT_PATH, WORKSPACE_ROOT, serializeSnapshot } from "./snapshot-schema.ts";

async function main(): Promise<void> {
  const install = spawnSync("bun", ["install"], { cwd: WORKSPACE_ROOT, stdio: "inherit" });
  if (install.status !== 0) throw new ContractLockError("bun install failed while locking the OMP contract");
  const { buildContractSnapshot } = await import("./snapshot-builder.ts");
  await writeFile(SNAPSHOT_PATH, serializeSnapshot(await buildContractSnapshot()), "utf8");
}

await main();
