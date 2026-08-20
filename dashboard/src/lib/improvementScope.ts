import type { HookResult } from "@/types/slopgate";

export const PATHLESS_SENTINEL = "__pathless__";
export const STRICT_MODE = "repo_strict";
const UNKNOWN_POLICY = "unknown_policy";
const UNKNOWN_VERSION = "unknown_version";

const FILE_MUTATION_TOOLS = new Set([
  "write",
  "edit",
  "multiedit",
  "notebookedit",
  "apply_patch",
  "applypatch",
]);
const SHELL_TOOLS = new Set(["bash", "powershell"]);
const SEARCH_TOOLS = new Set(["glob", "grep"]);
const WEB_TOOLS = new Set(["webfetch", "websearch", "web_fetch", "web_search"]);
const LIFECYCLE_NAMES = new Set(["stop", "sessionend", "subagentstop", "subagentstart", "sessionstart"]);
const THIRD_PARTY_DIRECTORIES = new Set([".venv", ".venvs", "venv", "env", "site-packages", "node_modules", ".tox", ".nox", ".eggs"]);
const ENFORCING_DECISIONS = new Set(["deny", "block"]);

export type ScopeConfidence = "high" | "medium" | "low";

export interface ImprovementRecord {
  index: number;
  session: string;
  timestamp: string;
  eventName: string;
  toolName: string;
  family: string;
  mutating: boolean;
  repoRoot: string | null;
  enforcementMode: string;
  targetPaths: string[];
  candidatePaths: string[];
  languages: string[];
  slopgateVersion: string | null;
  policyFingerprint: string | null;
  guidanceFingerprint: string | null;
  blockingRules: string[];
  erroredRules: Set<string>;
  hasErrors: boolean;
  pathsFromFindings: boolean;
  ruleTargetPaths: Record<string, string[]>;
}

function isObjectRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function optionalNonEmpty(value: string | null | undefined): string | null {
  return typeof value === "string" && value.length > 0 ? value : null;
}

export function semanticToolFamily(toolName: unknown, eventName: unknown): string {
  const tool = String(toolName ?? "").trim().toLowerCase();
  if (FILE_MUTATION_TOOLS.has(tool)) return "file_mutation";
  if (SHELL_TOOLS.has(tool)) return "shell";
  if (SEARCH_TOOLS.has(tool)) return "search";
  if (WEB_TOOLS.has(tool)) return "web";
  if (LIFECYCLE_NAMES.has(tool)) return "lifecycle";
  const event = String(eventName ?? "").trim().toLowerCase();
  return !tool && LIFECYCLE_NAMES.has(event) ? "lifecycle" : "other";
}

function normalizePosixPath(rawPath: string): string {
  const path = rawPath.replace(/\\/g, "/");
  const absolute = path.startsWith("/");
  const segments: string[] = [];
  for (const segment of path.split("/")) {
    if (!segment || segment === ".") continue;
    if (segment === "..") {
      const previous = segments[segments.length - 1];
      if (previous && previous !== "..") segments.pop();
      else if (!absolute) segments.push(segment);
      continue;
    }
    segments.push(segment);
  }
  const joined = segments.join("/");
  if (absolute) return joined ? `/${joined}` : "/";
  return joined || ".";
}

export function normalizeTargetPath(rawPath: string, repoRoot: string | null): string {
  const path = normalizePosixPath(rawPath);
  if (!repoRoot) return path;
  const root = normalizePosixPath(repoRoot);
  if (path === root) return ".";
  return path.startsWith(`${root}/`) ? path.slice(root.length + 1) : path;
}

function normalizedPathSet(rawPaths: readonly string[] | undefined, repoRoot: string | null): string[] {
  const normalized = new Set<string>();
  for (const rawPath of rawPaths ?? []) {
    if (!rawPath.trim()) continue;
    normalized.add(normalizeTargetPath(rawPath, repoRoot));
  }
  normalized.delete("");
  return [...normalized].sort();
}

function qualityMetadataPath(value: unknown): string | null {
  if (typeof value !== "string" || !value) return null;
  const normalized = value.replace(/\\/g, "/");
  if (normalized.toLowerCase() === "content" || normalized.toLowerCase() === "patch.diff") return null;
  if (normalized.split("/").some((part) => THIRD_PARTY_DIRECTORIES.has(part))) return null;
  return value;
}

function metadataHitPaths(metadata: Record<string, unknown> | undefined): string[] {
  const hits = metadata?.hits;
  if (!Array.isArray(hits)) return [];
  const paths: string[] = [];
  for (const hit of hits) {
    const path = typeof hit === "string" ? qualityMetadataPath(hit) : isObjectRecord(hit) ? qualityMetadataPath(hit.path) : null;
    if (path && !paths.includes(path)) paths.push(path);
  }
  return paths;
}

function findingPath(metadata: Record<string, unknown> | undefined): string | null {
  const direct = qualityMetadataPath(metadata?.path);
  return direct ?? metadataHitPaths(metadata)[0] ?? null;
}

function blockingFindingData(
  result: HookResult,
  repoRoot: string | null,
): { rules: string[]; paths: string[]; rulePaths: Record<string, string[]> } {
  const rules: string[] = [];
  const implicated: string[] = [];
  const rulePaths: Record<string, string[]> = {};
  for (const finding of result.findings) {
    if (!finding.decision || !ENFORCING_DECISIONS.has(finding.decision)) continue;
    if (!rules.includes(finding.rule_id)) rules.push(finding.rule_id);
    const directPath = findingPath(finding.metadata);
    if (directPath && !implicated.includes(directPath)) implicated.push(directPath);
    const paths: string[] = directPath ? [directPath] : [];
    for (const hitPath of metadataHitPaths(finding.metadata)) {
      if (!implicated.includes(hitPath)) implicated.push(hitPath);
      if (!paths.includes(hitPath)) paths.push(hitPath);
    }
    if (paths.length > 0) rulePaths[finding.rule_id] = [...(rulePaths[finding.rule_id] ?? []), ...paths];
  }
  return {
    rules,
    paths: normalizedPathSet(implicated, repoRoot),
    rulePaths: Object.fromEntries(
      Object.entries(rulePaths).map(([rule, paths]) => [rule, normalizedPathSet(paths, repoRoot)]),
    ),
  };
}

function errorRuleIds(errors: readonly string[]): Set<string> {
  const rules = new Set<string>();
  for (const error of errors) {
    const separator = error.indexOf(":");
    if (separator <= 0) continue;
    const prefix = error.slice(0, separator).trim();
    if (prefix) rules.add(prefix);
  }
  return rules;
}

export function parseImprovementRecord(result: HookResult, index: number): ImprovementRecord {
  const repoRoot = optionalNonEmpty(result.resolved_repo_root);
  const blocking = blockingFindingData(result, repoRoot);
  const candidatePaths = normalizedPathSet(result.candidate_paths, repoRoot);
  const pathsFromFindings = blocking.paths.length > 0;
  const targetPaths = pathsFromFindings ? blocking.paths : candidatePaths.length > 0 ? candidatePaths : [PATHLESS_SENTINEL];
  const errors = result.errors ?? [];
  return {
    index,
    session: result.session_id,
    timestamp: result.timestamp,
    eventName: result.event_name,
    toolName: result.tool_name,
    family: semanticToolFamily(result.tool_name, result.event_name),
    mutating: result.mutating === true,
    repoRoot,
    enforcementMode: String(result.enforcement_mode ?? "unknown"),
    targetPaths,
    candidatePaths,
    languages: [...(result.languages ?? [])],
    slopgateVersion: optionalNonEmpty(result.slopgate_version),
    policyFingerprint: optionalNonEmpty(result.effective_policy_fingerprint),
    guidanceFingerprint: optionalNonEmpty(result.guidance_fingerprint),
    blockingRules: blocking.rules,
    erroredRules: errorRuleIds(errors),
    hasErrors: errors.length > 0,
    pathsFromFindings,
    ruleTargetPaths: Object.fromEntries(
      blocking.rules.map((rule) => [rule, blocking.rulePaths[rule] ?? candidatePaths]),
    ),
  };
}

function timestampSortKey(timestamp: string): { rank: number; value: string } {
  const milliseconds = Date.parse(timestamp);
  return Number.isNaN(milliseconds) ? { rank: 1, value: timestamp } : { rank: 0, value: new Date(milliseconds).toISOString() };
}

export function parseImprovementRecords(results: readonly HookResult[]): ImprovementRecord[] {
  const records = results
    .map(parseImprovementRecord)
    .filter((record) => !record.session.startsWith("fixture-") && !record.session.startsWith("test-"));
  records.sort((left, right) => {
    const leftKey = timestampSortKey(left.timestamp);
    const rightKey = timestampSortKey(right.timestamp);
    if (leftKey.rank !== rightKey.rank) return leftKey.rank - rightKey.rank;
    if (leftKey.value !== rightKey.value) return leftKey.value < rightKey.value ? -1 : 1;
    return left.index - right.index;
  });
  return records;
}

export function structuralScopeKey(record: ImprovementRecord): string {
  return JSON.stringify([record.session, record.repoRoot ?? "", record.family, record.targetPaths]);
}

export function structuralScopeKeyForRule(record: ImprovementRecord, ruleId: string): string {
  return JSON.stringify([
    record.session,
    record.repoRoot ?? "",
    record.family,
    record.ruleTargetPaths[ruleId] ?? record.targetPaths,
  ]);
}

export function provenanceKey(record: ImprovementRecord): string {
  return JSON.stringify([
    record.enforcementMode,
    record.slopgateVersion ?? UNKNOWN_VERSION,
    record.policyFingerprint ?? UNKNOWN_POLICY,
    record.guidanceFingerprint ?? UNKNOWN_POLICY,
  ]);
}

export function canonicalResultScopeKey(result: HookResult): string {
  const record = parseImprovementRecord(result, 0);
  return JSON.stringify([structuralScopeKey(record), provenanceKey(record)]);
}

export function isLegacyRecord(record: ImprovementRecord): boolean {
  return (
    record.policyFingerprint === null
    || record.guidanceFingerprint === null
    || record.slopgateVersion === null
  );
}

export function recordScopeConfidence(record: ImprovementRecord): ScopeConfidence {
  if (record.targetPaths.length === 1 && record.targetPaths[0] === PATHLESS_SENTINEL) return "low";
  return record.pathsFromFindings ? "high" : "medium";
}
