import type { HookResult } from "@/types/slopgate";

const TERMINAL_EVENTS = new Set(["Stop", "SubagentStop", "SessionEnd", "TaskCompleted"]);
const NON_FINAL_METADATA_PATHS = new Set(["content", "patch.diff"]);
const MAX_RECOVERY_FINDINGS = 64;
const MAX_RECOVERY_CANDIDATE_PATHS = 32;
const MAX_RECOVERY_COLLECTOR_VARIANTS = 16;
const MAX_RECOVERY_CHAINS_PER_EVENT = 256;

type ChainStatus = "recovered" | "abandoned" | "open";

type Chain = {
  readonly key: string;
  readonly sessionId: string;
  readonly repoRoot: string;
  readonly ruleKey: string;
  readonly target: string;
  status: ChainStatus;
};

export type RecoveryMetrics = {
  readonly chains: number;
  readonly recovered: number;
  readonly abandoned: number;
  readonly open: number;
  readonly eventualRecoveryRate: number | null;
};

type ResultFinding = HookResult["findings"][number];

function isBlocking(finding: ResultFinding): boolean {
  return finding.decision === "block" || finding.decision === "deny";
}

function normalizedStrings(value: unknown, limit: number): readonly string[] {
  if (!Array.isArray(value)) return [];
  const unique = new Set<string>();
  for (const item of value) {
    if (typeof item !== "string") continue;
    const normalized = item.trim();
    if (normalized) unique.add(normalized);
  }
  return [...unique].slice(0, limit);
}

function findingRuleKeys(finding: ResultFinding): readonly string[] {
  const collectors = finding.metadata?.failing_collectors;
  if (finding.rule_id === "QUALITY-LINT-001") {
    const variants = normalizedStrings(collectors, MAX_RECOVERY_COLLECTOR_VARIANTS);
    if (variants.length > 0) return variants.map((variant) => `${finding.rule_id}\u0000${variant}`);
  }
  return [finding.rule_id];
}

function qualityMetadataPath(value: unknown): string | null {
  if (typeof value !== "string" || value.length === 0) return null;
  return NON_FINAL_METADATA_PATHS.has(value.replaceAll("\\", "/").toLowerCase()) ? null : value;
}

function metadataHitPath(hit: unknown): string | null {
  if (typeof hit === "string") return qualityMetadataPath(hit);
  if (typeof hit !== "object" || hit === null || Array.isArray(hit) || !("path" in hit)) return null;
  return qualityMetadataPath(hit.path);
}

function effectiveMetadataPath(finding: ResultFinding): string | null {
  const direct = qualityMetadataPath(finding.metadata?.path);
  if (direct) return direct;
  const hits = finding.metadata?.hits;
  if (!Array.isArray(hits)) return null;
  for (const hit of hits) {
    const path = metadataHitPath(hit);
    if (path) return path;
  }
  return null;
}

function fallbackTargets(result: HookResult): readonly string[] {
  if (result.resolved_repo_root) return [`repo:${result.resolved_repo_root}`];
  return [`session:${result.session_id}`];
}

function findingTargets(result: HookResult, finding: ResultFinding): readonly string[] {
  const path = effectiveMetadataPath(finding);
  if (path) return [path];
  const candidatePaths = normalizedStrings(result.candidate_paths, MAX_RECOVERY_CANDIDATE_PATHS);
  if (candidatePaths.length > 0) return candidatePaths;
  return fallbackTargets(result);
}

function resultTargets(result: HookResult): readonly string[] {
  const targets = new Set(normalizedStrings(result.candidate_paths, MAX_RECOVERY_CANDIDATE_PATHS));
  for (const finding of result.findings.slice(0, MAX_RECOVERY_FINDINGS)) {
    const path = effectiveMetadataPath(finding);
    if (path) targets.add(path);
  }
  return targets.size > 0 ? [...targets] : fallbackTargets(result);
}

function chainKey(result: HookResult, ruleKey: string, target: string): string {
  return [result.session_id, result.resolved_repo_root ?? "", result.enforcement_mode ?? "", ruleKey, target].join("\u0000");
}

export function computeRecoveryMetrics(results: readonly HookResult[]): RecoveryMetrics {
  const active = new Map<string, Chain>();
  const chains: Chain[] = [];
  const ordered = [...results]
    .filter((result) => result.trace_schema_version === 2 && result.enforcement_mode === "repo_strict")
    .sort((left, right) => left.timestamp.localeCompare(right.timestamp));

  for (const result of ordered) {
    if (TERMINAL_EVENTS.has(result.event_name)) {
      for (const [key, chain] of active) {
        if (chain.sessionId === result.session_id) {
          chain.status = "abandoned";
          active.delete(key);
        }
      }
      continue;
    }

    const targets = new Set(resultTargets(result));
    const retainedFindings = result.findings.slice(0, MAX_RECOVERY_FINDINGS);
    const blockingFindings = retainedFindings.filter(isBlocking);
    for (const [key, chain] of active) {
      const sameScope = chain.sessionId === result.session_id && chain.repoRoot === (result.resolved_repo_root ?? "");
      if (!sameScope || !targets.has(chain.target)) continue;
      const recovered =
        result.event_name === "PostToolUse" && result.tool_outcome === "success" && blockingFindings.length === 0;
      if (recovered) {
        chain.status = "recovered";
        active.delete(key);
      }
    }

    let created = 0;
    findingLoop: for (const finding of blockingFindings) {
      for (const ruleKey of findingRuleKeys(finding)) {
        for (const target of findingTargets(result, finding)) {
          if (created >= MAX_RECOVERY_CHAINS_PER_EVENT) break findingLoop;
          const key = chainKey(result, ruleKey, target);
          if (active.has(key)) continue;
          const chain: Chain = {
            key,
            sessionId: result.session_id,
            repoRoot: result.resolved_repo_root ?? "",
            ruleKey,
            target,
            status: "open",
          };
          active.set(key, chain);
          chains.push(chain);
          created++;
        }
      }
    }
  }

  const recovered = chains.filter((chain) => chain.status === "recovered").length;
  const abandoned = chains.filter((chain) => chain.status === "abandoned").length;
  const open = chains.length - recovered - abandoned;
  const observable = recovered + abandoned;
  return {
    chains: chains.length,
    recovered,
    abandoned,
    open,
    eventualRecoveryRate: observable > 0 ? (recovered / observable) * 100 : null,
  };
}
