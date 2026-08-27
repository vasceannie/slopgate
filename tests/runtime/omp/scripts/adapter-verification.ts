import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";

import { ContractLockError, isRecord, type ContractSnapshot } from "./snapshot-schema.ts";

const PYTHON_ADAPTER_PARSER = String.raw`
import ast
import json
import sys
from pathlib import Path


def fail(message: str) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(1)


module = ast.parse(Path(sys.argv[1]).read_text(encoding="utf8"))
assignments = [
    statement.value
    for statement in module.body
    if isinstance(statement, ast.Assign)
    and len(statement.targets) == 1
    and isinstance(statement.targets[0], ast.Name)
    and statement.targets[0].id == "_OMP_EVENT_ALIASES"
]
assignments.extend(
    statement.value
    for statement in module.body
    if isinstance(statement, ast.AnnAssign)
    and isinstance(statement.target, ast.Name)
    and statement.target.id == "_OMP_EVENT_ALIASES"
)
if len(assignments) != 1 or not isinstance(assignments[0], ast.Dict):
    fail("_OMP_EVENT_ALIASES must be a literal string-to-string dict")

aliases = []
for key, value in zip(assignments[0].keys, assignments[0].values, strict=True):
    if (
        not isinstance(key, ast.Constant)
        or not isinstance(key.value, str)
        or not isinstance(value, ast.Constant)
        or not isinstance(value.value, str)
    ):
        fail("_OMP_EVENT_ALIASES must be a literal string-to-string dict")
    aliases.append(key.value)

if len(aliases) != len(set(aliases)):
    fail("_OMP_EVENT_ALIASES contains duplicate event keys")
print(json.dumps({"aliases": aliases}, sort_keys=True))
`;

export function verifyAdapter(repoRoot: string, snapshot: ContractSnapshot): void {
  const adapterPath = join(repoRoot, "src", "slopgate", "adapters", "omp.py");
  if (!existsSync(adapterPath)) throw new ContractLockError(`missing OMP adapter: ${adapterPath}`);

  const result = spawnSync("python3", ["-c", PYTHON_ADAPTER_PARSER, adapterPath], {
    encoding: "utf8",
  });
  if (result.error) throw new ContractLockError(`failed to execute Python AST parser: ${result.error.message}`);
  if (result.status !== 0) {
    const detail = result.stderr.trim() || "Python AST parser failed";
    throw new ContractLockError(detail);
  }

  const parsed: unknown = JSON.parse(result.stdout);
  if (!isRecord(parsed) || !Array.isArray(parsed["aliases"])) {
    throw new ContractLockError("Python AST parser returned an invalid alias payload");
  }
  for (const alias of parsed["aliases"]) {
    if (typeof alias !== "string") {
      throw new ContractLockError("Python AST parser returned a non-string event key");
    }
    if (!snapshot.events.names.includes(alias)) {
      throw new ContractLockError(`adapter event "${alias}" is absent from the snapshot`);
    }
  }
}
