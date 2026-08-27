import { readFile } from "node:fs/promises";

import { buildContractSnapshot } from "./snapshot-builder.ts";
import {
  ContractLockError,
  SNAPSHOT_PATH,
  serializeSnapshot,
  type ContractSnapshot,
} from "./snapshot-schema.ts";

export async function verifyLockedSnapshot(): Promise<ContractSnapshot> {
  const snapshot = await buildContractSnapshot();
  const committed = await readFile(SNAPSHOT_PATH, "utf8");
  if (serializeSnapshot(snapshot) !== committed) {
    throw new ContractLockError("contract snapshot is stale; run bun run lock");
  }
  return snapshot;
}
