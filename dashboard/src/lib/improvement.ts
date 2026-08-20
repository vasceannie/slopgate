import type { HookResult } from "@/types/slopgate";
import {
  type ImprovementRecord,
  isLegacyRecord,
  parseImprovementRecords,
  provenanceKey,
  recordScopeConfidence,
  type ScopeConfidence,
  STRICT_MODE,
  structuralScopeKey,
  structuralScopeKeyForRule,
} from "./improvementScope";

export type EpisodeState = "resolved" | "still_failing" | "no_observed_followup" | "provenance_changed" | "evaluation_error";

export interface RepairEpisode {
  ruleId: string;
  anchor: ImprovementRecord;
  state: EpisodeState;
  followups: number;
  lastEnforcing: boolean;
  lastError: boolean;
  provenanceDivergence: boolean;
  resolvedRecord: ImprovementRecord | null;
}

export interface ImprovementEvaluation {
  records: ImprovementRecord[];
  episodes: RepairEpisode[];
  firstObserved: ImprovementRecord[];
}

export interface RepairSuccessSummary {
  rate: number | null;
  numerator: number;
  denominator: number;
  censored: {
    no_observed_followup: number;
    provenance_changed: number;
    evaluation_error: number;
  };
}

function createEpisode(ruleId: string, anchor: ImprovementRecord): RepairEpisode {
  return {
    ruleId,
    anchor,
    state: "no_observed_followup",
    followups: 0,
    lastEnforcing: false,
    lastError: false,
    provenanceDivergence: false,
    resolvedRecord: null,
  };
}

function classifyFollowup(episode: RepairEpisode, record: ImprovementRecord): boolean {
  if (record.blockingRules.includes(episode.ruleId)) {
    episode.lastEnforcing = true;
    episode.lastError = false;
    return false;
  }
  if (record.erroredRules.has(episode.ruleId)) {
    episode.lastError = true;
    episode.lastEnforcing = false;
    return false;
  }
  episode.state = "resolved";
  episode.resolvedRecord = record;
  return true;
}

function advanceEpisodes(bucket: Map<string, RepairEpisode>, record: ImprovementRecord, closed: RepairEpisode[]): void {
  for (const [ruleId, episode] of [...bucket.entries()]) {
    if (provenanceKey(record) !== provenanceKey(episode.anchor)) {
      episode.provenanceDivergence = true;
      episode.state = "provenance_changed";
      closed.push(episode);
      bucket.delete(ruleId);
      continue;
    }
    episode.followups += 1;
    if (classifyFollowup(episode, record)) {
      closed.push(episode);
      bucket.delete(ruleId);
    }
  }
}

function anchorEpisodes(
  open: Map<string, Map<string, RepairEpisode>>,
  record: ImprovementRecord,
  existing: Map<string, RepairEpisode> | undefined,
  key: string,
): void {
  if (record.blockingRules.length === 0) return;
  const bucket = existing ?? new Map<string, RepairEpisode>();
  if (!existing) open.set(key, bucket);
  for (const ruleId of record.blockingRules) {
    if (!bucket.has(ruleId)) bucket.set(ruleId, createEpisode(ruleId, record));
  }
}

function closeEpisode(episode: RepairEpisode): RepairEpisode {
  if (episode.state === "provenance_changed") {
    return episode;
  }
  if (episode.followups > 0) {
    episode.state = episode.lastError ? "evaluation_error" : "still_failing";
  } else if (episode.provenanceDivergence) {
    episode.state = "provenance_changed";
  } else {
    episode.state = "no_observed_followup";
  }
  return episode;
}

function firstObserved(records: readonly ImprovementRecord[]): ImprovementRecord[] {
  const seen = new Set<string>();
  const first: ImprovementRecord[] = [];
  for (const record of records) {
    if (!record.mutating) continue;
    const key = JSON.stringify([structuralScopeKey(record), provenanceKey(record)]);
    if (seen.has(key)) continue;
    seen.add(key);
    first.push(record);
  }
  return first;
}

export function evaluateImprovement(results: readonly HookResult[]): ImprovementEvaluation {
  const records = parseImprovementRecords(results);
  const open = new Map<string, Map<string, RepairEpisode>>();
  const closed: RepairEpisode[] = [];
  for (const record of records) {
    if (record.blockingRules.length > 0) {
      const ruleKeys = new Map(
        record.blockingRules.map((ruleId) => [ruleId, structuralScopeKeyForRule(record, ruleId)]),
      );
      for (const key of new Set(ruleKeys.values())) {
        const bucket = open.get(key);
        if (bucket) advanceEpisodes(bucket, record, closed);
        const rulesForKey = record.blockingRules.filter((ruleId) => ruleKeys.get(ruleId) === key);
        anchorEpisodes(open, { ...record, blockingRules: rulesForKey }, bucket, key);
      }
    } else {
      const key = structuralScopeKey(record);
      const bucket = open.get(key);
      if (bucket) advanceEpisodes(bucket, record, closed);
    }
  }
  for (const bucket of open.values()) {
    for (const episode of bucket.values()) closed.push(closeEpisode(episode));
  }
  closed.sort((left, right) => left.anchor.index - right.anchor.index);
  return { records, episodes: closed, firstObserved: firstObserved(records) };
}

function episodeCounts(episodes: readonly RepairEpisode[]): Record<EpisodeState, number> {
  const counts: Record<EpisodeState, number> = {
    resolved: 0,
    still_failing: 0,
    no_observed_followup: 0,
    provenance_changed: 0,
    evaluation_error: 0,
  };
  for (const episode of episodes) counts[episode.state] += 1;
  return counts;
}

function roundTo(value: number, precision: number): number {
  const factor = 10 ** precision;
  return Math.round(value * factor) / factor;
}

function rate(numerator: number, denominator: number): { rate: number | null; numerator: number; denominator: number } {
  return { rate: denominator > 0 ? roundTo(numerator / denominator, 4) : null, numerator, denominator };
}

export function repairSuccessSummary(episodes: readonly RepairEpisode[]): RepairSuccessSummary {
  const counts = episodeCounts(episodes);
  const summary = rate(counts.resolved, counts.resolved + counts.still_failing);
  return {
    ...summary,
    censored: {
      no_observed_followup: counts.no_observed_followup,
      provenance_changed: counts.provenance_changed,
      evaluation_error: counts.evaluation_error,
    },
  };
}

export function episodeScopeConfidenceCounts(episodes: readonly RepairEpisode[]): Record<ScopeConfidence, number> {
  const counts: Record<ScopeConfidence, number> = { high: 0, medium: 0, low: 0 };
  for (const episode of episodes) counts[recordScopeConfidence(episode.anchor)] += 1;
  return counts;
}

function episodeAttempts(episode: RepairEpisode): number {
  return episode.resolvedRecord ? episode.followups : 0;
}

function episodeLatencyMs(episode: RepairEpisode): number | null {
  if (!episode.resolvedRecord) return null;
  const start = Date.parse(episode.anchor.timestamp);
  const end = Date.parse(episode.resolvedRecord.timestamp);
  return Number.isNaN(start) || Number.isNaN(end) ? null : roundTo(end - start, 1);
}

function percentile(values: readonly number[], fraction: number): number | null {
  if (values.length === 0) return null;
  const ordered = [...values].sort((left, right) => left - right);
  if (ordered.length === 1) return roundTo(ordered[0], 1);
  const position = (ordered.length - 1) * fraction;
  const lower = Math.floor(position);
  const upper = Math.ceil(position);
  if (lower === upper) return roundTo(ordered[lower], 1);
  const weight = position - lower;
  return roundTo(ordered[lower] * (1 - weight) + ordered[upper] * weight, 1);
}

function isNumber(value: number | null): value is number {
  return value !== null;
}

export function buildImprovementFixtureSummary(results: readonly HookResult[]) {
  const evaluation = evaluateImprovement(results);
  const strictRecords = evaluation.records.filter((record) => record.enforcementMode === STRICT_MODE);
  const strictEpisodes = evaluation.episodes.filter((episode) => episode.anchor.enforcementMode === STRICT_MODE);
  const mutating = strictRecords.filter((record) => record.mutating);
  const blocked = mutating.filter((record) => record.blockingRules.length > 0).length;
  const strictFirst = evaluation.firstObserved.filter((record) => record.enforcementMode === STRICT_MODE);
  const cleanFirst = strictFirst.filter((record) => record.blockingRules.length === 0).length;
  const resolved = strictEpisodes.filter((episode) => episode.resolvedRecord !== null);
  const blockingValue = mutating.length > 0 ? roundTo((100 * blocked) / mutating.length, 2) : null;
  return {
    authoritative: evaluation.records.some((record) => !isLegacyRecord(record)),
    legacy_rows: evaluation.records.filter(isLegacyRecord).length,
    episodes: episodeCounts(evaluation.episodes),
    headline: {
      blocking_per_100_mutations: { value: blockingValue, numerator: blocked, denominator: mutating.length },
      first_attempt_clean_rate: rate(cleanFirst, strictFirst.length),
      repair_success_rate: repairSuccessSummary(strictEpisodes),
      median_repair_attempts: percentile(resolved.map(episodeAttempts), 0.5),
      median_repair_latency_ms: percentile(resolved.map(episodeLatencyMs).filter(isNumber), 0.5),
    },
  };
}
