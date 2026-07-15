import { useMemo } from "react";
import { useTraceDataSource } from "@/context/useTraceDataSource";
import { mockConfig } from "@/data/mockTraces";
import { computeRecoveryMetrics } from "@/lib/recoveryMetrics";
import type { NativeSessionIds, SessionData, SessionGroup } from "@/lib/sessionHelpers";
import type {
  Decision,
  EventName,
  FilterState,
  HookEvent,
  HookResult,
  LineageConfidence,
  LineageRole,
  OperationalContext,
  OperationalCountRow,
  Platform,
  PlatformSource,
  RuleFinding,
  Severity,
  SubprocessRun,
  TraceMetadata,
} from "@/types/slopgate";

function getWindowMs(w: string): number {
  const map: Record<string, number> = {
    "1h": 3600000,
    "6h": 21600000,
    "24h": 86400000,
    "7d": 604800000,
    "30d": 2592000000,
  };
  return map[w] || 604800000;
}

function filterByTime<T extends { timestamp: string }>(items: T[], windowMs: number): T[] {
  const cutoff = new Date(Date.now() - windowMs).toISOString();
  return items.filter((i) => i.timestamp >= cutoff);
}

function filterByPlatform<T extends { platform?: Platform }>(items: T[], platforms: Platform[]): T[] {
  if (platforms.length === 0) return items;
  return items.filter((i) => i.platform && platforms.includes(i.platform));
}

function filterByPath<T extends { session_id: string }>(
  items: T[],
  pathFilter: string | null,
  sessionIdsTouchingPath: Set<string> | null,
): T[] {
  if (!pathFilter || !sessionIdsTouchingPath) return items;
  return items.filter((i) => sessionIdsTouchingPath.has(i.session_id));
}

function isSelfTestSessionId(sessionId: string): boolean {
  return sessionId.startsWith("self-test-");
}

function filterOutSelfTestSessions<T extends { session_id: string }>(items: T[]): T[] {
  return items.filter((item) => !isSelfTestSessionId(item.session_id));
}

export function resolveDecision(findings: Array<{ decision?: Decision | null }>): Decision {
  if (findings.length === 0) return "allow";
  if (findings.some((f) => f.decision === "block")) return "block";
  if (findings.some((f) => f.decision === "deny")) return "deny";
  if (findings.some((f) => f.decision === "ask")) return "ask";
  if (findings.some((f) => f.decision === "warn")) return "warn";
  if (findings.some((f) => f.decision === "context")) return "context";
  if (findings.some((f) => f.decision === "info")) return "info";
  return "allow";
}

function latestTimestamp(items: Array<{ timestamp?: string }>): string | null {
  let latest: string | null = null;
  for (const item of items) {
    if (typeof item.timestamp !== "string" || !item.timestamp) continue;
    if (latest === null || item.timestamp > latest) latest = item.timestamp;
  }
  return latest;
}

export function streamSchemaValidationWarning(rejectedStreamRecords: number, acceptedStreamRecords: number): string | null {
  if (rejectedStreamRecords <= 0 || acceptedStreamRecords > 0) return null;
  return `${rejectedStreamRecords} streamed record${rejectedStreamRecords === 1 ? "" : "s"} failed dashboard schema validation.`;
}

type CountRow = OperationalCountRow;

function emptyDecisionCounts(): Record<Decision, number> {
  return {
    allow: 0,
    deny: 0,
    block: 0,
    ask: 0,
    context: 0,
    warn: 0,
    info: 0,
  };
}

function topCounts(values: Array<string | null | undefined>, limit = 6): CountRow[] {
  const counts = new Map<string, number>();
  for (const raw of values) {
    const label = typeof raw === "string" && raw.trim() ? raw.trim() : "unknown";
    counts.set(label, (counts.get(label) ?? 0) + 1);
  }
  return Array.from(counts.entries())
    .sort(([, a], [, b]) => b - a)
    .slice(0, limit)
    .map(([label, count]) => ({ label, count }));
}

function shortPath(path: string | null | undefined): string {
  if (!path) return "unknown";
  const parts = path.split("/").filter(Boolean);
  if (parts.length <= 2) return path;
  return parts.slice(-2).join("/");
}

function traceDecision(result: HookResult): Decision {
  return resolveDecision(result.findings);
}

export type TopRuleSummary = {
  rule_id: string;
  count: number;
  severity: Severity;
  decisions: Partial<Record<Decision, number>>;
};

function enforcementDecisionCount(decisions: Partial<Record<Decision, number>>): number {
  return (decisions.block ?? 0) + (decisions.deny ?? 0);
}

export function summarizeTopRules(rules: RuleFinding[], limit = Number.POSITIVE_INFINITY): TopRuleSummary[] {
  const firstSeen = new Map<string, number>();
  const ruleCounts = rules.reduce(
    (acc: Record<string, number>, r: RuleFinding, index: number) => {
      if (!firstSeen.has(r.rule_id)) firstSeen.set(r.rule_id, index);
      acc[r.rule_id] = (acc[r.rule_id] || 0) + 1;
      return acc;
    },
    {} as Record<string, number>,
  );
  const ruleDetails = rules.reduce(
    (acc: Record<string, { severity: Severity; decisions: Record<Decision, number> }>, r: RuleFinding) => {
      if (!acc[r.rule_id])
        acc[r.rule_id] = {
          severity: r.severity,
          decisions: emptyDecisionCounts(),
        };
      const dec = r.decision ?? "context";
      acc[r.rule_id].decisions[dec] = (acc[r.rule_id].decisions[dec] || 0) + 1;
      return acc;
    },
    {} as Record<string, { severity: Severity; decisions: Record<Decision, number> }>,
  );

  return (Object.entries(ruleCounts) as Array<[string, number]>)
    .map(([rule_id, count]) => {
      const details = ruleDetails[rule_id];
      return {
        rule_id,
        count,
        severity: details?.severity ?? "LOW",
        decisions: details?.decisions ?? emptyDecisionCounts(),
        firstSeen: firstSeen.get(rule_id) ?? Number.MAX_SAFE_INTEGER,
      };
    })
    .sort((a, b) => {
      const aEnforcement = enforcementDecisionCount(a.decisions);
      const bEnforcement = enforcementDecisionCount(b.decisions);
      if (aEnforcement > 0 || bEnforcement > 0) {
        return (
          bEnforcement - aEnforcement ||
          (b.decisions.block ?? 0) - (a.decisions.block ?? 0) ||
          (b.decisions.deny ?? 0) - (a.decisions.deny ?? 0) ||
          b.count - a.count ||
          a.firstSeen - b.firstSeen
        );
      }
      return b.count - a.count || a.firstSeen - b.firstSeen;
    })
    .slice(0, limit)
    .map(({ rule_id, count, severity, decisions }) => ({
      rule_id,
      count,
      severity,
      decisions,
    }));
}

interface SessionAggregate {
  platform: Platform;
  events: HookEvent[];
  findings: RuleFinding[];
  results: HookResult[];
  subprocesses: SubprocessRun[];
}

interface SessionSummary extends SessionAggregate, SessionData {
  id: string;
  eventCount: number;
  tools: string[];
  languages: string[];
  pathCount: number;
  finalOutcome: Decision;
  duration: number;
  latestTimestamp: number;
}

interface TraceSessionIndexes {
  sessions: SessionData[];
  sessionGroups: SessionGroup[];
  sessionDecisions: Map<string, Decision[]>;
  sessionPathCounts: Map<string, number>;
  hottestRepos: Array<{ repo: string; count: number }>;
}

function sessionBucket(sessionMap: Map<string, SessionAggregate>, sessionId: string, platform: Platform): SessionAggregate {
  let bucket = sessionMap.get(sessionId);
  if (!bucket) {
    bucket = {
      platform,
      events: [],
      findings: [],
      results: [],
      subprocesses: [],
    };
    sessionMap.set(sessionId, bucket);
  } else if (bucket.platform === "unknown" && platform !== "unknown") {
    bucket.platform = platform;
  }
  return bucket;
}

function finalOutcomeFor(decisions: Decision[]): Decision {
  if (decisions.includes("block")) return "block";
  if (decisions.includes("deny")) return "deny";
  if (decisions.includes("ask")) return "ask";
  return "allow";
}

function repoLabelForPath(path: string): string {
  const segments = path.split("/").filter(Boolean);
  for (const marker of ["repos", "workspace-hooker"]) {
    const markerIndex = segments.indexOf(marker);
    if (markerIndex >= 0 && markerIndex + 1 < segments.length) {
      return segments[markerIndex + 1];
    }
  }
  if (segments.length >= 3 && segments[0] === "home") return segments[2];
  return segments[0] || path;
}

type LineageRecord = TraceMetadata & { platform?: Platform; timestamp?: string };

function sessionRecords(data: SessionAggregate): LineageRecord[] {
  return [...data.events, ...data.findings, ...data.results];
}

function firstString(records: LineageRecord[], key: keyof TraceMetadata): string | null | undefined {
  for (const record of records) {
    const value = record[key];
    if (typeof value === "string" && value.trim()) return value;
    if (value === null) return null;
  }
  return undefined;
}

function uniqueStrings(values: Array<string | null | undefined>): string[] {
  const seen = new Set<string>();
  for (const value of values) {
    const trimmed = value?.trim();
    if (trimmed) seen.add(trimmed);
  }
  return Array.from(seen);
}

function traceSecondaryIds(records: LineageRecord[]): string[] {
  return uniqueStrings(records.flatMap((record) => record.secondary_session_ids ?? []));
}

function mergeSecondaryIds(sessions: SessionData[]): string[] {
  return uniqueStrings(sessions.flatMap((session) => session.secondaryIds ?? []));
}

function nativeSessionIds(records: LineageRecord[]): NativeSessionIds | undefined {
  const opencode = firstString(records, "opencode_session_id");
  const codex = firstString(records, "codex_session_id");
  return opencode || codex ? { opencode, codex } : undefined;
}

function mergeNativeSessionIds(sessions: SessionData[]): NativeSessionIds | undefined {
  const opencode = uniqueStrings(sessions.map((session) => session.nativeSessionIds?.opencode))[0];
  const codex = uniqueStrings(sessions.map((session) => session.nativeSessionIds?.codex))[0];
  const claude = uniqueStrings(sessions.map((session) => session.nativeSessionIds?.claude))[0];
  return opencode || codex || claude ? { opencode, codex, claude } : undefined;
}

function firstPlatform(records: LineageRecord[]): Platform | null | undefined {
  for (const record of records) {
    const value = record.origin_platform;
    if (value) return value;
    if (value === null) return null;
  }
  return undefined;
}

function firstPlatformSource(records: LineageRecord[]): PlatformSource | null | undefined {
  for (const record of records) {
    const value = record.platform_source;
    if (value) return value;
    if (value === null) return null;
  }
  return undefined;
}

function firstLineageRole(records: LineageRecord[]): LineageRole | null | undefined {
  for (const record of records) {
    const value = record.lineage_role;
    if (value) return value;
    if (value === null) return null;
  }
  return undefined;
}

function lineageConfidenceFor(
  lineage: Pick<SessionData, "parentSessionId" | "rootSessionId" | "originSessionId" | "originPlatform" | "lineageRole">,
): LineageConfidence {
  return lineage.parentSessionId ||
    lineage.rootSessionId ||
    lineage.originSessionId ||
    lineage.originPlatform ||
    (lineage.lineageRole && lineage.lineageRole !== "raw")
    ? "explicit"
    : "none";
}

function deriveLineageRole(
  recordRole: LineageRole | null | undefined,
  parentSessionId: string | null | undefined,
  originSessionId: string | null | undefined,
): LineageRole | null {
  if (recordRole) return recordRole;
  if (parentSessionId && originSessionId) return "child_mirror";
  if (parentSessionId) return "child";
  if (originSessionId) return "mirror";
  return "raw";
}

function sessionPlatformList(records: LineageRecord[], fallback: Platform): Platform[] {
  const platforms = new Set<Platform>();
  for (const record of records) {
    if (record.platform) platforms.add(record.platform);
    if (record.origin_platform) platforms.add(record.origin_platform);
  }
  platforms.add(fallback);
  return Array.from(platforms).sort();
}

function lineageRootFor(session: SessionData): string {
  return session.rootSessionId || session.parentSessionId || session.originSessionId || session.id;
}

function uniqueSessions<T extends SessionData>(sessions: T[]): T[] {
  const seen = new Set<string>();
  return sessions.filter((session) => {
    if (seen.has(session.id)) return false;
    seen.add(session.id);
    return true;
  });
}

function timestampMs(item: { timestamp?: string }): number {
  const parsed = Date.parse(item.timestamp ?? "");
  return Number.isFinite(parsed) ? parsed : 0;
}

function sortByTimestamp<T extends { timestamp?: string }>(items: T[]): T[] {
  return [...items].sort((a, b) => timestampMs(a) - timestampMs(b));
}

const INFERRED_MIRROR_START_WINDOW_MS = 3000;
const INFERRED_MIRROR_END_WINDOW_MS = 10000;
const INFERRED_CHILD_WINDOW_SLACK_MS = 5000;
const INFERRED_CHILD_MIN_PARENT_EXTRA_MS = 30000;
const INFERRED_CHILD_PARENT_DURATION_MULTIPLIER = 3;

type InferredLineageRole = "child" | "mirror";

interface SessionTimeRange {
  start: number;
  end: number;
  duration: number;
}

function timestampRangeForItems(items: Array<{ timestamp?: string }>): SessionTimeRange | null {
  let start = Number.POSITIVE_INFINITY;
  let end = Number.NEGATIVE_INFINITY;
  for (const item of items) {
    const timestamp = timestampMs(item);
    if (timestamp <= 0) continue;
    if (timestamp < start) start = timestamp;
    if (timestamp > end) end = timestamp;
  }
  if (!Number.isFinite(start) || !Number.isFinite(end)) return null;
  return { start, end, duration: Math.max(0, end - start) };
}

interface InferredRelation {
  parentId: string;
  role: InferredLineageRole;
}

function sessionTimeRange(session: SessionSummary): SessionTimeRange | null {
  return timestampRangeForItems([...session.events, ...session.findings, ...session.results, ...session.subprocesses]);
}

function meaningfulSessionPath(path: string): string | null {
  const trimmed = path.trim();
  if (!trimmed || trimmed === "/" || trimmed === "." || trimmed === ",") {
    return null;
  }
  return trimmed;
}

function sessionPathSet(session: SessionSummary): Set<string> {
  const paths = new Set<string>();
  for (const event of session.events) {
    for (const path of event.candidate_paths ?? []) {
      const meaningfulPath = meaningfulSessionPath(path);
      if (meaningfulPath) paths.add(meaningfulPath);
    }
  }
  return paths;
}

function sharedPathCount(left: Set<string>, right: Set<string>): number {
  let count = 0;
  const [smaller, larger] = left.size <= right.size ? [left, right] : [right, left];
  for (const path of smaller) {
    if (larger.has(path)) count++;
  }
  return count;
}

function hasExplicitLineage(session: SessionSummary): boolean {
  return session.lineageConfidence === "explicit";
}

function platformPreference(session: SessionSummary): number {
  const platforms = new Set(session.platforms ?? [session.platform]);
  if (platforms.has("opencode")) return 0;
  if (platforms.has("codex")) return 1;
  if (platforms.has("cursor")) return 2;
  if (platforms.has("claude")) return 3;
  return 4;
}

function preferredInferredPrimary(left: SessionSummary, right: SessionSummary): SessionSummary {
  const leftRank = platformPreference(left);
  const rightRank = platformPreference(right);
  if (leftRank !== rightRank) return leftRank < rightRank ? left : right;
  if (left.duration !== right.duration) {
    return left.duration > right.duration ? left : right;
  }
  if (left.eventCount !== right.eventCount) {
    return left.eventCount > right.eventCount ? left : right;
  }
  if (left.latestTimestamp !== right.latestTimestamp) {
    return left.latestTimestamp > right.latestTimestamp ? left : right;
  }
  return left.id.localeCompare(right.id) <= 0 ? left : right;
}

function nativeIdentityKeys(session: SessionSummary): string[] {
  return uniqueStrings([
    session.nativeSessionIds?.opencode ? `opencode:${session.nativeSessionIds.opencode}` : null,
    session.nativeSessionIds?.codex ? `codex:${session.nativeSessionIds.codex}` : null,
  ]);
}

function sharedNativeIdentityRoots(sessions: SessionSummary[]): Map<string, string> {
  const sessionsByNativeId = new Map<string, SessionSummary[]>();
  for (const session of sessions) {
    for (const nativeId of nativeIdentityKeys(session)) {
      const matching = sessionsByNativeId.get(nativeId) ?? [];
      matching.push(session);
      sessionsByNativeId.set(nativeId, matching);
    }
  }

  const roots = new Map<string, string>();
  for (const matching of sessionsByNativeId.values()) {
    if (matching.length < 2) continue;
    const primary = matching.reduce(preferredInferredPrimary);
    for (const session of matching) roots.set(session.id, primary.id);
  }
  return roots;
}

function hasSharedNativeIdentity(sessions: SessionSummary[]): boolean {
  const seen = new Set<string>();
  for (const session of sessions) {
    for (const nativeId of nativeIdentityKeys(session)) {
      if (seen.has(nativeId)) return true;
      seen.add(nativeId);
    }
  }
  return false;
}

function canInferMirrorRelation(
  left: SessionSummary,
  right: SessionSummary,
  ranges: Map<string, SessionTimeRange>,
  pathSets: Map<string, Set<string>>,
): boolean {
  const leftRange = ranges.get(left.id);
  const rightRange = ranges.get(right.id);
  if (!leftRange || !rightRange) return false;
  const startDelta = Math.abs(leftRange.start - rightRange.start);
  const endDelta = Math.abs(leftRange.end - rightRange.end);
  const sharedPaths = sharedPathCount(pathSets.get(left.id) ?? new Set<string>(), pathSets.get(right.id) ?? new Set<string>());
  return startDelta <= INFERRED_MIRROR_START_WINDOW_MS && endDelta <= INFERRED_MIRROR_END_WINDOW_MS && sharedPaths > 0;
}

function canInferChildRelation(
  parent: SessionSummary,
  child: SessionSummary,
  ranges: Map<string, SessionTimeRange>,
  pathSets: Map<string, Set<string>>,
): boolean {
  const parentRange = ranges.get(parent.id);
  const childRange = ranges.get(child.id);
  if (!parentRange || !childRange) return false;
  if (
    childRange.start < parentRange.start - INFERRED_CHILD_WINDOW_SLACK_MS ||
    childRange.end > parentRange.end + INFERRED_CHILD_WINDOW_SLACK_MS
  ) {
    return false;
  }
  const minimumParentDuration = Math.max(
    childRange.duration * INFERRED_CHILD_PARENT_DURATION_MULTIPLIER,
    childRange.duration + INFERRED_CHILD_MIN_PARENT_EXTRA_MS,
  );
  if (parentRange.duration < minimumParentDuration) return false;
  return sharedPathCount(pathSets.get(parent.id) ?? new Set<string>(), pathSets.get(child.id) ?? new Set<string>()) > 0;
}

function relationParentScore(parent: SessionSummary, child: SessionSummary): number {
  const parentRangeBonus = Math.max(0, parent.duration - child.duration) / 1000;
  return parentRangeBonus - platformPreference(parent) * 100;
}

function inferHistoricalRelations(sessions: SessionSummary[]): Map<string, InferredRelation> {
  const rawSessions = sessions.filter((session) => !hasExplicitLineage(session));
  const ranges = new Map<string, SessionTimeRange>();
  const pathSets = new Map<string, Set<string>>();
  for (const session of rawSessions) {
    const range = sessionTimeRange(session);
    if (range) ranges.set(session.id, range);
    pathSets.set(session.id, sessionPathSet(session));
  }
  const relations = new Map<string, InferredRelation>();

  for (let leftIndex = 0; leftIndex < rawSessions.length; leftIndex++) {
    for (let rightIndex = leftIndex + 1; rightIndex < rawSessions.length; rightIndex++) {
      const left = rawSessions[leftIndex];
      const right = rawSessions[rightIndex];
      if (!canInferMirrorRelation(left, right, ranges, pathSets)) continue;
      const primary = preferredInferredPrimary(left, right);
      const related = primary.id === left.id ? right : left;
      if (!relations.has(related.id)) {
        relations.set(related.id, { parentId: primary.id, role: "mirror" });
      }
    }
  }

  for (const child of rawSessions) {
    if (relations.has(child.id)) continue;
    let bestParent: SessionSummary | null = null;
    let bestScore = Number.NEGATIVE_INFINITY;
    for (const parent of rawSessions) {
      if (parent.id === child.id) continue;
      if (!canInferChildRelation(parent, child, ranges, pathSets)) continue;
      const score = relationParentScore(parent, child);
      if (score > bestScore) {
        bestScore = score;
        bestParent = parent;
      }
    }
    if (bestParent) {
      relations.set(child.id, { parentId: bestParent.id, role: "child" });
    }
  }

  return relations;
}

function inferredRootFor(sessionId: string, relations: Map<string, InferredRelation>): string {
  let root = sessionId;
  const seen = new Set<string>();
  while (!seen.has(root)) {
    seen.add(root);
    const relation = relations.get(root);
    if (!relation) return root;
    root = relation.parentId;
  }
  return sessionId;
}

function withInferredRole(session: SessionSummary, relation: InferredRelation | undefined): SessionSummary {
  if (!relation) return session;
  return {
    ...session,
    lineageRole: relation.role,
    lineageConfidence: "inferred",
  };
}

function mergeGroupSession(group: SessionGroup, sessionsById: Map<string, SessionSummary>): SessionSummary {
  const primary = sessionsById.get(group.primarySession.id);
  if (!primary) {
    throw new Error(`Missing primary session for group ${group.id}`);
  }
  const sourceSessions = uniqueSessions(
    group.rawSessionIds.flatMap((id) => {
      const session = sessionsById.get(id);
      return session ? [session] : [];
    }),
  );
  const sessionsToMerge = sourceSessions.length > 0 ? sourceSessions : [primary];
  const events = sortByTimestamp(sessionsToMerge.flatMap((session) => session.events));
  const findings = sortByTimestamp(sessionsToMerge.flatMap((session) => session.findings));
  const results = sortByTimestamp(sessionsToMerge.flatMap((session) => session.results));
  const subprocesses = sortByTimestamp(sessionsToMerge.flatMap((session) => session.subprocesses));
  const tools = [...new Set(events.map((event) => event.tool_name).filter(Boolean))];
  const languages = [...new Set(events.flatMap((event) => event.languages ?? []))];
  const pathCount = new Set(events.flatMap((event) => event.candidate_paths ?? [])).size;
  const range = timestampRangeForItems([...events, ...findings, ...results, ...subprocesses]);
  const duration = range?.duration ?? 0;
  const latestTimestamp = range?.end ?? primary.latestTimestamp;
  const decisions = [...results.map(traceDecision), ...findings.map((finding) => finding.decision ?? "context")];
  const titledSession = sessionsToMerge.find((session) => session.title);
  const secondaryIds = mergeSecondaryIds(sessionsToMerge);
  const platform =
    primary.platform === "unknown" ? (group.platforms.find((item) => item !== "unknown") ?? primary.platform) : primary.platform;

  return {
    ...primary,
    title: primary.title ?? titledSession?.title ?? null,
    titleSource: primary.titleSource ?? titledSession?.titleSource ?? null,
    sessionIdentitySource:
      primary.sessionIdentitySource ?? sessionsToMerge.find((session) => session.sessionIdentitySource)?.sessionIdentitySource ?? null,
    secondaryIds,
    nativeSessionIds: mergeNativeSessionIds(sessionsToMerge),
    platform,
    events,
    findings,
    results,
    subprocesses,
    childSessions: group.childSessions,
    mirrorSessions: group.mirrorSessions,
    rawSessionIds: group.rawSessionIds,
    platforms: group.platforms,
    lineageConfidence: group.lineageConfidence,
    eventCount: events.length,
    tools,
    languages,
    pathCount,
    finalOutcome: finalOutcomeFor(decisions),
    duration,
    latestTimestamp,
  };
}

function buildSessionGroups(sessions: SessionSummary[]): SessionGroup[] {
  const inferredRelations = inferHistoricalRelations(sessions);
  const nativeIdentityRoots = sharedNativeIdentityRoots(sessions);
  const buckets = new Map<string, SessionSummary[]>();
  for (const session of sessions) {
    const root = hasExplicitLineage(session)
      ? lineageRootFor(session)
      : (nativeIdentityRoots.get(session.id) ?? inferredRootFor(session.id, inferredRelations));
    const bucket = buckets.get(root) ?? [];
    bucket.push(session);
    buckets.set(root, bucket);
  }
  return Array.from(buckets.entries())
    .map(([id, groupedSessions]) => {
      const primarySession =
        groupedSessions.find((session) => session.id === id) ??
        groupedSessions.find((session) => session.lineageRole === "parent") ??
        groupedSessions[0];
      const related = groupedSessions.filter((session) => session.id !== primarySession.id);
      const childSessions = related.filter(
        (session) =>
          session.lineageRole === "child" ||
          session.lineageRole === "child_mirror" ||
          Boolean(session.parentSessionId) ||
          inferredRelations.get(session.id)?.role === "child",
      );
      const mirrorSessions = related.filter(
        (session) =>
          session.lineageRole === "mirror" ||
          session.lineageRole === "child_mirror" ||
          Boolean(session.originSessionId) ||
          inferredRelations.get(session.id)?.role === "mirror",
      );
      const platforms = Array.from(new Set(groupedSessions.flatMap((session) => session.platforms ?? [session.platform]))).sort();
      const confidence: LineageConfidence =
        groupedSessions.some((session) => session.lineageConfidence === "explicit") || hasSharedNativeIdentity(groupedSessions)
          ? "explicit"
          : groupedSessions.length > 1
            ? "inferred"
            : "none";
      return {
        id,
        primarySession,
        childSessions: uniqueSessions(childSessions.map((session) => withInferredRole(session, inferredRelations.get(session.id)))),
        mirrorSessions: uniqueSessions(mirrorSessions.map((session) => withInferredRole(session, inferredRelations.get(session.id)))),
        rawSessionIds: groupedSessions.map((session) => session.id),
        lineageConfidence: confidence,
        platforms,
      };
    })
    .sort((a, b) => b.primarySession.latestTimestamp - a.primarySession.latestTimestamp);
}

export function buildTraceSessionIndexes(
  events: HookEvent[],
  rules: RuleFinding[],
  results: HookResult[],
  subprocesses: SubprocessRun[],
): TraceSessionIndexes {
  const sessionMap = new Map<string, SessionAggregate>();
  const sessionPathSets = new Map<string, Set<string>>();
  const repoCounts = new Map<string, number>();
  const sessionDecisions = new Map<string, Decision[]>();

  for (const event of events) {
    if (isSelfTestSessionId(event.session_id)) continue;
    sessionBucket(sessionMap, event.session_id, event.platform).events.push(event);
    const paths = event.candidate_paths ?? [];
    const sessionPaths = sessionPathSets.get(event.session_id) ?? new Set();
    for (const path of paths) sessionPaths.add(path);
    sessionPathSets.set(event.session_id, sessionPaths);
    for (const path of paths) {
      const repo = repoLabelForPath(path);
      repoCounts.set(repo, (repoCounts.get(repo) ?? 0) + 1);
    }
  }
  for (const rule of rules) {
    if (isSelfTestSessionId(rule.session_id)) continue;
    sessionBucket(sessionMap, rule.session_id, rule.platform).findings.push(rule);
  }
  for (const result of [...results].sort((a, b) => a.timestamp.localeCompare(b.timestamp))) {
    if (isSelfTestSessionId(result.session_id)) continue;
    sessionBucket(sessionMap, result.session_id, result.platform).results.push(result);
    const decisions = sessionDecisions.get(result.session_id) ?? [];
    decisions.push(traceDecision(result));
    sessionDecisions.set(result.session_id, decisions);
  }
  for (const subprocess of subprocesses) {
    if (isSelfTestSessionId(subprocess.session_id)) continue;
    sessionMap.get(subprocess.session_id)?.subprocesses.push(subprocess);
  }
  const sessions = Array.from(sessionMap.entries())
    .map(([id, data]) => {
      const records = sessionRecords(data);
      const sessionTitle = firstString(records, "session_title");
      const secondaryIds = traceSecondaryIds(records);
      const parentSessionId = firstString(records, "parent_session_id");
      const rootSessionId = firstString(records, "root_session_id");
      const originSessionId = firstString(records, "origin_session_id");
      const lineageRole = deriveLineageRole(firstLineageRole(records), parentSessionId, originSessionId);
      const lineageFields = {
        parentSessionId,
        rootSessionId,
        originPlatform: firstPlatform(records),
        originSessionId,
        lineageRole,
      };
      const tools = [...new Set(data.events.map((event) => event.tool_name).filter(Boolean))];
      const languages = [...new Set(data.events.flatMap((event) => event.languages ?? []))];
      const range = timestampRangeForItems(data.events);
      const duration = range?.duration ?? 0;
      const latestTimestamp = range?.end ?? 0;

      return {
        id,
        title: sessionTitle,
        titleSource: firstString(records, "session_title_source"),
        sessionIdentitySource: firstString(records, "session_identity_source"),
        secondaryIds,
        nativeSessionIds: nativeSessionIds(records),
        ...data,
        platforms: sessionPlatformList(records, data.platform),
        ...lineageFields,
        platformSource: firstPlatformSource(records),
        subagentType: firstString(records, "subagent_type"),
        spawnDescription: firstString(records, "spawn_description"),
        lineageConfidence: lineageConfidenceFor(lineageFields),
        rawSessionIds: [id],
        eventCount: data.events.length,
        tools,
        languages,
        pathCount: sessionPathSets.get(id)?.size ?? 0,
        finalOutcome: finalOutcomeFor(sessionDecisions.get(id) ?? []),
        duration,
        latestTimestamp,
      };
    })
    .sort((a, b) => b.latestTimestamp - a.latestTimestamp);
  const sessionGroups = buildSessionGroups(sessions);
  const sessionsById = new Map(sessions.map((session) => [session.id, session]));
  const groupedSessions = sessionGroups.map((group) => mergeGroupSession(group, sessionsById));

  return {
    sessions: groupedSessions,
    sessionGroups,
    sessionDecisions,
    sessionPathCounts: new Map(Array.from(sessionPathSets.entries()).map(([id, paths]) => [id, paths.size])),
    hottestRepos: Array.from(repoCounts.entries())
      .sort(([, a], [, b]) => b - a)
      .slice(0, 10)
      .map(([repo, count]) => ({ repo, count })),
  };
}

export function useTraceData(filters: FilterState) {
  const { data: rawData, sourceMode, streamState, isStreaming, sourceMeta } = useTraceDataSource();

  const windowMs = useMemo(() => getWindowMs(filters.timeWindow), [filters.timeWindow]);

  const { timeEvents, timeRules, timeResults, timeSubprocesses } = useMemo<{
    timeEvents: HookEvent[];
    timeRules: RuleFinding[];
    timeResults: HookResult[];
    timeSubprocesses: SubprocessRun[];
  }>(() => {
    const filteredTimeEvents: HookEvent[] = filterByTime(rawData.events, windowMs);
    const filteredTimeRules: RuleFinding[] = filterByTime(rawData.rules, windowMs);
    const filteredTimeResults: HookResult[] = filterByTime(rawData.results, windowMs);

    return {
      timeEvents: filterOutSelfTestSessions(filterByPlatform(filteredTimeEvents, filters.platforms)),
      timeRules: filterOutSelfTestSessions(filterByPlatform(filteredTimeRules, filters.platforms)),
      timeResults: filterOutSelfTestSessions(filterByPlatform(filteredTimeResults, filters.platforms)),
      timeSubprocesses: filterOutSelfTestSessions(filterByTime(rawData.subprocesses, windowMs)),
    };
  }, [filters.platforms, rawData, windowMs]);

  const { events, rules, results, subprocesses } = useMemo<{
    sessionIdsTouchingPath: Set<string> | null;
    events: HookEvent[];
    rules: RuleFinding[];
    results: HookResult[];
    subprocesses: SubprocessRun[];
  }>(() => {
    let nextSessionIdsTouchingPath: Set<string> | null = null;

    if (filters.pathFilter) {
      nextSessionIdsTouchingPath = new Set<string>();
      for (const e of timeEvents) {
        if ((e.candidate_paths ?? []).some((p: string) => p === filters.pathFilter || p.startsWith(`${filters.pathFilter}/`))) {
          nextSessionIdsTouchingPath.add(e.session_id);
        }
      }
    }

    return {
      sessionIdsTouchingPath: nextSessionIdsTouchingPath,
      events: filterByPath(timeEvents, filters.pathFilter, nextSessionIdsTouchingPath),
      rules: filterByPath(timeRules, filters.pathFilter, nextSessionIdsTouchingPath),
      results: filterByPath(timeResults, filters.pathFilter, nextSessionIdsTouchingPath),
      subprocesses:
        filters.pathFilter && nextSessionIdsTouchingPath
          ? timeSubprocesses.filter((s: SubprocessRun) => nextSessionIdsTouchingPath.has(s.session_id))
          : timeSubprocesses,
    };
  }, [filters.pathFilter, timeEvents, timeResults, timeRules, timeSubprocesses]);

  const { totalInvocations, decisionCounts, blockRate, denyRate, askRate, skippedCount, errorCount } = useMemo<{
    totalInvocations: number;
    decisionCounts: Record<Decision, number>;
    blockRate: number;
    denyRate: number;
    askRate: number;
    skippedCount: number;
    errorCount: number;
  }>(() => {
    const nextTotalInvocations = results.length;
    const nextDecisionCounts = emptyDecisionCounts();
    let nextSkippedCount = 0;
    let nextErrorCount = 0;
    for (const result of results) {
      nextDecisionCounts[resolveDecision(result.findings)]++;
      if (result.skipped) nextSkippedCount++;
      if ((result.errors ?? []).length > 0) nextErrorCount++;
    }

    return {
      totalInvocations: nextTotalInvocations,
      decisionCounts: nextDecisionCounts,
      blockRate: nextTotalInvocations ? ((nextDecisionCounts.block || 0) / nextTotalInvocations) * 100 : 0,
      denyRate: nextTotalInvocations ? ((nextDecisionCounts.deny || 0) / nextTotalInvocations) * 100 : 0,
      askRate: nextTotalInvocations ? ((nextDecisionCounts.ask || 0) / nextTotalInvocations) * 100 : 0,
      skippedCount: nextSkippedCount,
      errorCount: nextErrorCount,
    };
  }, [results]);

  const { sparklines } = useMemo<{
    sparklines: {
      invocations: number[];
      blockRate: number[];
      denyRate: number[];
      askRate: number[];
      skipped: number[];
      errors: number[];
    };
  }>(() => {
    const bucketCount = 12;
    const bucketSize = Math.max(windowMs / bucketCount, 1);
    const now = Date.now();
    const nextSparkBuckets = Array.from({ length: bucketCount }, () => ({
      invocations: 0,
      blocks: 0,
      denies: 0,
      asks: 0,
      total: 0,
      skipped: 0,
      errors: 0,
    }));

    for (const r of results) {
      const age = now - new Date(r.timestamp).getTime();
      const idx = Math.min(bucketCount - 1, Math.max(0, bucketCount - 1 - Math.floor(age / bucketSize)));
      nextSparkBuckets[idx].invocations++;
      nextSparkBuckets[idx].total++;
      const d = resolveDecision(r.findings);
      if (d === "block") nextSparkBuckets[idx].blocks++;
      if (d === "deny") nextSparkBuckets[idx].denies++;
      if (d === "ask") nextSparkBuckets[idx].asks++;
      if (r.skipped) nextSparkBuckets[idx].skipped++;
      if ((r.errors ?? []).length > 0) nextSparkBuckets[idx].errors++;
    }

    return {
      sparklines: {
        invocations: nextSparkBuckets.map((b) => b.invocations),
        blockRate: nextSparkBuckets.map((b) => (b.total ? (b.blocks / b.total) * 100 : 0)),
        denyRate: nextSparkBuckets.map((b) => (b.total ? (b.denies / b.total) * 100 : 0)),
        askRate: nextSparkBuckets.map((b) => (b.total ? (b.asks / b.total) * 100 : 0)),
        skipped: nextSparkBuckets.map((b) => b.skipped),
        errors: nextSparkBuckets.map((b) => b.errors),
      },
    };
  }, [results, windowMs]);

  const { eventsByType, eventsByTypeAndPlatform, timeSeries, topRules, duplicationByRule } = useMemo<{
    eventsByType: Record<EventName, number>;
    eventsByTypeAndPlatform: Record<EventName, Partial<Record<Platform, number>>>;
    timeSeries: Array<{ time: string } & Record<Decision, number>>;
    topRules: Array<{
      rule_id: string;
      count: number;
      severity: Severity;
      decisions: Partial<Record<Decision, number>>;
    }>;
    duplicationByRule: Array<{ rule_id: string; count: number }>;
  }>(() => {
    const nextEventsByType = events.reduce(
      (acc: Record<EventName, number>, e: HookEvent) => {
        acc[e.event_name] = (acc[e.event_name] || 0) + 1;
        return acc;
      },
      {} as Record<EventName, number>,
    );

    const nextEventsByTypeAndPlatform = events.reduce(
      (acc: Record<EventName, Partial<Record<Platform, number>>>, e: HookEvent) => {
        const platformCounts = acc[e.event_name] ?? {};
        platformCounts[e.platform] = (platformCounts[e.platform] ?? 0) + 1;
        acc[e.event_name] = platformCounts;
        return acc;
      },
      {} as Record<EventName, Partial<Record<Platform, number>>>,
    );

    const tsBucketSize = windowMs <= 86400000 ? 3600000 : 86400000;
    const timeSeriesBuckets = new Map<string, Record<Decision, number>>();
    for (const r of results) {
      const t = Math.floor(new Date(r.timestamp).getTime() / tsBucketSize) * tsBucketSize;
      const key = new Date(t).toISOString();
      let bucket = timeSeriesBuckets.get(key);
      if (!bucket) {
        bucket = emptyDecisionCounts();
        timeSeriesBuckets.set(key, bucket);
      }
      bucket[resolveDecision(r.findings)]++;
    }

    const dupRules = ["repeated-code-block", "duplicate-call-sequence", "semantic-clone"];
    const ruleCountById = new Map<string, number>();
    for (const rule of rules) {
      ruleCountById.set(rule.rule_id, (ruleCountById.get(rule.rule_id) ?? 0) + 1);
    }

    return {
      eventsByType: nextEventsByType,
      eventsByTypeAndPlatform: nextEventsByTypeAndPlatform,
      timeSeries: Array.from(timeSeriesBuckets.entries())
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([time, counts]) => ({ time, ...counts })),
      topRules: summarizeTopRules(rules),
      duplicationByRule: dupRules.map((id) => ({
        rule_id: id,
        count: ruleCountById.get(id) ?? 0,
      })),
    };
  }, [events, results, rules, windowMs]);

  const sessionIndexes = useMemo(() => {
    return buildTraceSessionIndexes(events, rules, results, subprocesses);
  }, [events, results, rules, subprocesses]);
  const { sessions, sessionGroups } = sessionIndexes;

  const { asyncPassCount, asyncFailCount, asyncByCommand, fireCounts } = useMemo<{
    asyncPassCount: number;
    asyncFailCount: number;
    asyncByCommand: Array<{
      command: string;
      total: number;
      pass: number;
      fail: number;
      medianRuntime: number;
      failures: string[];
    }>;
    fireCounts: Map<string, number>;
  }>(() => {
    let nextAsyncPassCount = 0;
    let nextAsyncFailCount = 0;
    const subprocessesByCommand = new Map<string, SubprocessRun[]>();
    for (const subprocess of subprocesses) {
      if (subprocess.returncode === 0) nextAsyncPassCount++;
      else nextAsyncFailCount++;
      const existing = subprocessesByCommand.get(subprocess.command) ?? [];
      existing.push(subprocess);
      subprocessesByCommand.set(subprocess.command, existing);
    }
    const nextAsyncByCommand = Array.from(subprocessesByCommand.entries())
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([command, matching]) => {
        let pass = 0;
        let fail = 0;
        const durations: number[] = [];
        const failures: string[] = [];
        for (const subprocess of matching) {
          durations.push(subprocess.duration_ms);
          if (subprocess.returncode === 0) {
            pass++;
          } else {
            fail++;
            if (failures.length < 3) failures.push(subprocess.stderr);
          }
        }
        return {
          command,
          total: matching.length,
          pass,
          fail,
          medianRuntime: median(durations),
          failures,
        };
      });

    const nextFireCounts = new Map<string, number>();
    for (const r of rules) nextFireCounts.set(r.rule_id, (nextFireCounts.get(r.rule_id) ?? 0) + 1);

    return {
      asyncPassCount: nextAsyncPassCount,
      asyncFailCount: nextAsyncFailCount,
      asyncByCommand: nextAsyncByCommand,
      fireCounts: nextFireCounts,
    };
  }, [rules, subprocesses]);

  const operationalContext = useMemo<OperationalContext>(() => {
    const traceRecords: TraceMetadata[] = results.length > 0 ? results : [...events, ...rules];
    const blockingResults = results.filter((r: HookResult) => {
      const decision = traceDecision(r);
      return decision === "block" || decision === "deny";
    });

    const recovery = computeRecoveryMetrics(results);

    const denialCounts = new Map<string, number>();
    for (const result of blockingResults) {
      const ruleIds = result.findings
        .filter((f) => f.decision === "block" || f.decision === "deny")
        .map((f) => f.rule_id || "unknown-rule");
      for (const ruleId of ruleIds.length > 0 ? ruleIds : ["unknown-rule"]) {
        const key = `${result.session_id.slice(0, 8)} · ${ruleId}`;
        denialCounts.set(key, (denialCounts.get(key) ?? 0) + 1);
      }
    }

    return {
      platformCapabilities: topCounts(traceRecords.map((r) => r.platform_capability)),
      enforcementModes: topCounts(traceRecords.map((r) => r.enforcement_mode)),
      degradedReasons: topCounts(traceRecords.map((r) => r.degraded_reason).filter(Boolean), 5),
      repoRoots: topCounts(
        traceRecords.map((r) => shortPath(r.resolved_repo_root)),
        5,
      ),
      pathlessResults: results.filter((r: HookResult) => (sessionIndexes.sessionPathCounts.get(r.session_id) ?? 0) === 0).length,
      repeatedDenials: Array.from(denialCounts.entries())
        .filter(([, count]) => count > 1)
        .sort(([, a], [, b]) => b - a)
        .slice(0, 5)
        .map(([label, count]) => ({ label, count })),
      eventualRecoveryRate: recovery.eventualRecoveryRate,
      recoveryChains: recovery.chains,
      recoveredChains: recovery.recovered,
      abandonedChains: recovery.abandoned,
      openChains: recovery.open,
    };
  }, [events, results, rules, sessionIndexes]);

  const sourceStatus = useMemo(() => {
    const windowStartAt = new Date(Date.now() - windowMs).toISOString();
    const latestByCategory = {
      events: latestTimestamp(rawData.events),
      rules: latestTimestamp(rawData.rules),
      results: latestTimestamp(rawData.results),
      subprocesses: latestTimestamp(rawData.subprocesses),
    };
    const windowRecordCount = timeEvents.length + timeRules.length + timeResults.length + timeSubprocesses.length;
    let warning: string | null = null;

    if (sourceMeta.snapshotError) {
      warning = `Live snapshot failed: ${sourceMeta.snapshotError}`;
    } else if (Object.keys(sourceMeta.snapshotTruncated).length > 0) {
      warning = `Live snapshot was truncated for browser safety: ${Object.entries(sourceMeta.snapshotTruncated)
        .map(([key, count]) => `${key} +${count}`)
        .join(", ")}.`;
    } else if (windowRecordCount === 0 && sourceMeta.latestDataAt && sourceMeta.latestDataAt < windowStartAt) {
      warning = `No accepted trace records in the selected ${filters.timeWindow} window; newest dataset record is ${sourceMeta.latestDataAt}.`;
    } else if (timeResults.length === 0 && latestByCategory.results && latestByCategory.results < windowStartAt) {
      warning = `No result records in the selected ${filters.timeWindow} window; newest result record is ${latestByCategory.results}.`;
    } else if (isStreaming && sourceMeta.acceptedStreamRecords === 0 && windowRecordCount === 0) {
      warning = "LIVE transport is connected, but no trace records have been accepted from the stream yet.";
    } else {
      warning = streamSchemaValidationWarning(sourceMeta.rejectedStreamRecords, sourceMeta.acceptedStreamRecords);
    }

    return {
      mode: sourceMode,
      streamState,
      isStreaming,
      isSnapshotLoading: sourceMeta.isSnapshotLoading,
      windowStartAt,
      latestByCategory,
      warning,
      meta: sourceMeta,
    };
  }, [
    filters.timeWindow,
    isStreaming,
    rawData.events,
    rawData.results,
    rawData.rules,
    rawData.subprocesses,
    sourceMeta,
    sourceMode,
    streamState,
    timeEvents.length,
    timeResults.length,
    timeRules.length,
    timeSubprocesses.length,
    windowMs,
  ]);

  return useMemo(
    () => ({
      unfilteredEvents: timeEvents,
      unfilteredRules: timeRules,
      events,
      rules,
      results,
      subprocesses,
      posture: {
        totalInvocations,
        blockRate,
        denyRate,
        askRate,
        skippedCount,
        errorCount,
        decisionCounts,
        sparklines,
      },
      sourceStatus,
      eventsByType,
      eventsByTypeAndPlatform,
      timeSeries,
      topRules,
      duplicationByRule,
      sessions,
      sessionGroups,
      async: {
        passCount: asyncPassCount,
        failCount: asyncFailCount,
        byCommand: asyncByCommand,
      },
      drift: {
        config: mockConfig,
        hottestRepos: sessionIndexes.hottestRepos,
        operationalContext,
      },
      fireCounts,
    }),
    [
      asyncByCommand,
      asyncFailCount,
      asyncPassCount,
      askRate,
      blockRate,
      decisionCounts,
      denyRate,
      duplicationByRule,
      errorCount,
      events,
      eventsByType,
      eventsByTypeAndPlatform,
      fireCounts,
      operationalContext,
      results,
      rules,
      sessions,
      sessionGroups,
      sessionIndexes,
      skippedCount,
      sourceStatus,
      sparklines,
      subprocesses,
      timeEvents,
      timeRules,
      timeSeries,
      topRules,
      totalInvocations,
    ],
  );
}

function median(arr: number[]): number {
  if (arr.length === 0) return 0;
  const sorted = [...arr].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}
