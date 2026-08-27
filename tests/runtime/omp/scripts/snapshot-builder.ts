import { spawnSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { join } from "node:path";

import {
  ContractLockError,
  WORKSPACE_ROOT,
  isRecord,
  type ContractSnapshot,
  type IdentityEvidence,
} from "./snapshot-schema.ts";
import { extractTypeContract } from "./type-extraction.ts";
import { assertCanonicalStopTextCases } from "./session-stop-text.ts";

const CODING_AGENT = "@oh-my-pi/pi-coding-agent";
const PI_TUI = "@oh-my-pi/pi-tui";

async function readJson(path: string): Promise<unknown> {
  return JSON.parse(await readFile(path, "utf8"));
}

async function packageVersion(packageRoot: string, expectedName: string): Promise<string> {
  const packageJson = await readJson(join(packageRoot, "package.json"));
  if (!isRecord(packageJson) || packageJson["name"] !== expectedName || typeof packageJson["version"] !== "string") {
    throw new ContractLockError(`invalid package metadata for ${expectedName}`);
  }
  return packageJson["version"];
}

function resolveExportTypes(exportsMap: Record<string, unknown>, subpath: string): string {
  for (const [pattern, rawTarget] of Object.entries(exportsMap)) {
    if (!isRecord(rawTarget) || typeof rawTarget["types"] !== "string") continue;
    if (pattern === subpath) return rawTarget["types"];
    const marker = pattern.indexOf("*");
    if (marker < 0) continue;
    const prefix = pattern.slice(0, marker);
    const suffix = pattern.slice(marker + 1);
    if (!subpath.startsWith(prefix) || !subpath.endsWith(suffix)) continue;
    const wildcard = subpath.slice(prefix.length, subpath.length - suffix.length);
    return rawTarget["types"].replace("*", wildcard);
  }
  throw new ContractLockError(`package exports do not expose ${subpath}`);
}

async function exportContract(packageRoot: string): Promise<ContractSnapshot["exports"]> {
  const packageJson = await readJson(join(packageRoot, "package.json"));
  const exportsMap = isRecord(packageJson) && isRecord(packageJson["exports"]) ? packageJson["exports"] : undefined;
  if (!exportsMap) throw new ContractLockError("coding-agent package has no exports map");
  const runnerSubpath = "./extensibility/extensions/runner";
  const loaderSubpath = "./extensibility/extensions/loader";
  return {
    ExtensionRunner: { subpath: runnerSubpath, types: resolveExportTypes(exportsMap, runnerSubpath) },
    ExtensionRuntime: { subpath: loaderSubpath, types: resolveExportTypes(exportsMap, loaderSubpath) },
    loadExtensionFromFactory: { subpath: loaderSubpath, types: resolveExportTypes(exportsMap, loaderSubpath) },
  };
}

async function identityContract(): Promise<{
  readonly evidence: IdentityEvidence | null;
  readonly source: "ctx.sessionManager.getSessionId()" | null;
}> {
  const relativePath = "scripts/session-identity.test.ts";
  const path = join(WORKSPACE_ROOT, relativePath);
  const sha256 = createHash("sha256").update(await readFile(path)).digest("hex");
  const proof = spawnSync(process.execPath, ["run", relativePath], { cwd: WORKSPACE_ROOT, encoding: "utf8" });
  if (proof.status !== 0) return { evidence: null, source: null };
  return {
    evidence: {
      assertions: ["same-within-session", "distinct-across-sessions"],
      kind: "runner-test",
      path: relativePath,
      sha256,
    },
    source: "ctx.sessionManager.getSessionId()",
  };
}

export async function buildContractSnapshot(): Promise<ContractSnapshot> {
  assertCanonicalStopTextCases();
  const codingAgentRoot = join(WORKSPACE_ROOT, "node_modules", "@oh-my-pi", "pi-coding-agent");
  const piTuiRoot = join(WORKSPACE_ROOT, "node_modules", "@oh-my-pi", "pi-tui");
  const [codingAgentVersion, piTuiVersion, exportsContract, identity] = await Promise.all([
    packageVersion(codingAgentRoot, CODING_AGENT),
    packageVersion(piTuiRoot, PI_TUI),
    exportContract(codingAgentRoot),
    identityContract(),
  ]);
  if (codingAgentVersion !== "18.0.5" || piTuiVersion !== "18.0.5") {
    throw new ContractLockError("OMP package versions must remain pinned to 18.0.5");
  }
  const extracted = extractTypeContract(codingAgentRoot);
  return {
    bash_input: extracted.bashInput,
    events: {
      names: extracted.eventNames,
      user_bash: extracted.eventNames.includes("user_bash"),
      user_python: extracted.eventNames.includes("user_python"),
    },
    exports: exportsContract,
    listeners: extracted.listeners,
    packages: { [CODING_AGENT]: codingAgentVersion, [PI_TUI]: piTuiVersion },
    results: extracted.results,
    schema_version: 1,
    session_identity_evidence: identity.evidence,
    session_identity_source: identity.source,
    session_stop: {
      agent_message_content_union: extracted.sessionStopContentUnion,
      event: extracted.sessionStopEvent,
    },
    session_stop_response_source: "last_assistant_message",
  };
}
