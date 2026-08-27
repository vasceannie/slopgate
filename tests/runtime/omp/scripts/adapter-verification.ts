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


def collect_assignments(parsed_module: ast.Module) -> tuple[set[str], dict[str, str]]:
    bound_names = set()
    string_constants = {}
    ambiguous_names = set()
    for statement in parsed_module.body:
        name = None
        value = None
        if (
            isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
        ):
            name = statement.targets[0].id
            value = statement.value
        elif isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
            name = statement.target.id
            value = statement.value
        if name is None:
            continue
        if name in bound_names:
            ambiguous_names.add(name)
            string_constants.pop(name, None)
            continue
        bound_names.add(name)
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            string_constants[name] = value.value
    for name in ambiguous_names:
        string_constants.pop(name, None)
    return bound_names, string_constants


module = ast.parse(Path(sys.argv[1]).read_text(encoding="utf8"))
local_names, local_strings = collect_assignments(module)
constant_imports = {
    imported.name
    for statement in module.body
    if isinstance(statement, ast.ImportFrom)
    and statement.level == 0
    and statement.module == "slopgate.constants"
    for imported in statement.names
    if imported.asname is None and imported.name != "*"
}
imported_names = set()
imported_strings = {}
if constant_imports:
    constants_path = Path(sys.argv[2])
    if not constants_path.is_file():
        fail(f"missing slopgate constants: {constants_path}")
    constants_module = ast.parse(constants_path.read_text(encoding="utf8"))
    imported_names, imported_strings = collect_assignments(constants_module)


def resolve_name(name: str) -> str:
    local_binding = name in local_names
    imported_binding = name in constant_imports
    if local_binding == imported_binding:
        fail(f'_OMP_EVENT_ALIASES value "{name}" must resolve to a string constant')
    if local_binding:
        value = local_strings.get(name)
    else:
        value = imported_strings.get(name) if name in imported_names else None
    if value is None:
        fail(f'_OMP_EVENT_ALIASES value "{name}" must resolve to a string constant')
    return value


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
    if not isinstance(key, ast.Constant) or not isinstance(key.value, str):
        fail("_OMP_EVENT_ALIASES must be a literal string-to-string dict")
    if isinstance(value, ast.Constant) and isinstance(value.value, str):
        resolved_value = value.value
    elif isinstance(value, ast.Name):
        resolved_value = resolve_name(value.id)
    else:
        fail("_OMP_EVENT_ALIASES must be a literal string-to-string dict")
    if not isinstance(resolved_value, str):
        fail("_OMP_EVENT_ALIASES must be a literal string-to-string dict")
    aliases.append(key.value)

if len(aliases) != len(set(aliases)):
    fail("_OMP_EVENT_ALIASES contains duplicate event keys")
print(json.dumps({"aliases": aliases}, sort_keys=True))
`;

export function verifyAdapter(repoRoot: string, snapshot: ContractSnapshot): void {
  const adapterPath = join(repoRoot, "src", "slopgate", "adapters", "omp.py");
  const constantsPath = join(repoRoot, "src", "slopgate", "constants.py");
  if (!existsSync(adapterPath)) throw new ContractLockError(`missing OMP adapter: ${adapterPath}`);

  const result = spawnSync("python3", ["-c", PYTHON_ADAPTER_PARSER, adapterPath, constantsPath], {
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
