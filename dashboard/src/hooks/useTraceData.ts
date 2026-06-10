import { useMemo } from "react";
import { useTraceDataSource } from "@/context/useTraceDataSource";
import type {
  FilterState, HookEvent, RuleFinding, HookResult, SubprocessRun,
  Decision, Platform, EventName, Severity, TraceMetadata, OperationalContext, OperationalCountRow,
} from "@/types/slopgate";
import { mockConfig } from "@/data/mockTraces";

function getWindowMs(w: string): number {
  const map: Record<string, number> = {
    "1h": 3600000, "6h": 21600000, "24h": 86400000,
    "7d": 604800000, "30d": 2592000000,
  };
  return map[w] || 604800000;
}

function filterByTime<T extends { timestamp: string }>(items: T[], windowMs: number): T[] {
  const cutoff = new Date(Date.now() - windowMs).toISOString();
  return items.filter(i => i.timestamp >= cutoff);
}

function filterByPlatform<T extends { platform?: Platform }>(items: T[], platforms: Platform[]): T[] {
  if (platforms.length === 0) return items;
  return items.filter(i => i.platform && platforms.includes(i.platform));
}

function filterByPath<T extends { session_id: string }>(
  items: T[],
  pathFilter: string | null,
  sessionIdsTouchingPath: Set<string> | null
): T[] {
  if (!pathFilter || !sessionIdsTouchingPath) return items;
  return items.filter(i => sessionIdsTouchingPath.has(i.session_id));
}

export function resolveDecision(findings: Array<{ decision?: Decision | null }>): Decision {
  if (findings.length === 0) return "allow";
  if (findings.some(f => f.decision === "block")) return "block";
  if (findings.some(f => f.decision === "deny")) return "deny";
  if (findings.some(f => f.decision === "ask")) return "ask";
  if (findings.some(f => f.decision === "warn")) return "warn";
  if (findings.some(f => f.decision === "context")) return "context";
  if (findings.some(f => f.decision === "info")) return "info";
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

type CountRow = OperationalCountRow;

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
  const ruleCounts = rules.reduce((acc: Record<string, number>, r: RuleFinding, index: number) => {
    if (!firstSeen.has(r.rule_id)) firstSeen.set(r.rule_id, index);
    acc[r.rule_id] = (acc[r.rule_id] || 0) + 1;
    return acc;
  }, {} as Record<string, number>);
  const ruleDetails = rules.reduce((acc: Record<string, { severity: Severity; decisions: Record<Decision, number> }>, r: RuleFinding) => {
    if (!acc[r.rule_id]) acc[r.rule_id] = { severity: r.severity, decisions: {} as Record<Decision, number> };
    const dec = r.decision ?? "context";
    acc[r.rule_id].decisions[dec] = (acc[r.rule_id].decisions[dec] || 0) + 1;
    return acc;
  }, {} as Record<string, { severity: Severity; decisions: Record<Decision, number> }>);

  return (Object.entries(ruleCounts) as Array<[string, number]>)
    .map(([rule_id, count]) => ({
      rule_id,
      count,
      severity: ruleDetails[rule_id]?.severity || "LOW" as Severity,
      decisions: ruleDetails[rule_id]?.decisions || {},
      firstSeen: firstSeen.get(rule_id) ?? Number.MAX_SAFE_INTEGER,
    }))
    .sort((a, b) => {
      const aEnforcement = enforcementDecisionCount(a.decisions);
      const bEnforcement = enforcementDecisionCount(b.decisions);
      if (aEnforcement > 0 || bEnforcement > 0) {
        return bEnforcement - aEnforcement
          || (b.decisions.block ?? 0) - (a.decisions.block ?? 0)
          || (b.decisions.deny ?? 0) - (a.decisions.deny ?? 0)
          || b.count - a.count
          || a.firstSeen - b.firstSeen;
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
      timeEvents: filterByPlatform(filteredTimeEvents, filters.platforms),
      timeRules: filterByPlatform(filteredTimeRules, filters.platforms),
      timeResults: filterByPlatform(filteredTimeResults, filters.platforms),
      timeSubprocesses: filterByTime(rawData.subprocesses, windowMs),
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
        if ((e.candidate_paths ?? []).some((p: string) => p === filters.pathFilter || p.startsWith(filters.pathFilter + "/"))) {
          nextSessionIdsTouchingPath.add(e.session_id);
        }
      }
    }

    return {
      sessionIdsTouchingPath: nextSessionIdsTouchingPath,
      events: filterByPath(timeEvents, filters.pathFilter, nextSessionIdsTouchingPath),
      rules: filterByPath(timeRules, filters.pathFilter, nextSessionIdsTouchingPath),
      results: filterByPath(timeResults, filters.pathFilter, nextSessionIdsTouchingPath),
      subprocesses: filters.pathFilter && nextSessionIdsTouchingPath
        ? timeSubprocesses.filter((s: SubprocessRun) => nextSessionIdsTouchingPath.has(s.session_id))
        : timeSubprocesses,
    };
  }, [filters.pathFilter, timeEvents, timeResults, timeRules, timeSubprocesses]);

  const {
    totalInvocations,
    decisionCounts,
    blockRate,
    denyRate,
    askRate,
    skippedCount,
    errorCount,
  } = useMemo<{
    totalInvocations: number;
    decisionCounts: Record<Decision, number>;
    blockRate: number;
    denyRate: number;
    askRate: number;
    skippedCount: number;
    errorCount: number;
  }>(() => {
    const nextTotalInvocations = results.length;
    const nextDecisionCounts = results.reduce((acc: Record<Decision, number>, r: HookResult) => {
      acc[resolveDecision(r.findings)]++;
      return acc;
    }, { allow: 0, deny: 0, block: 0, ask: 0, context: 0, warn: 0, info: 0 } as Record<Decision, number>);

    return {
      totalInvocations: nextTotalInvocations,
      decisionCounts: nextDecisionCounts,
      blockRate: nextTotalInvocations ? ((nextDecisionCounts.block || 0) / nextTotalInvocations * 100) : 0,
      denyRate: nextTotalInvocations ? ((nextDecisionCounts.deny || 0) / nextTotalInvocations * 100) : 0,
      askRate: nextTotalInvocations ? ((nextDecisionCounts.ask || 0) / nextTotalInvocations * 100) : 0,
      skippedCount: results.filter((r: HookResult) => r.skipped).length,
      errorCount: results.filter((r: HookResult) => (r.errors ?? []).length > 0).length,
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
      invocations: 0, blocks: 0, denies: 0, asks: 0, total: 0, skipped: 0, errors: 0,
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
        invocations: nextSparkBuckets.map(b => b.invocations),
        blockRate: nextSparkBuckets.map(b => b.total ? (b.blocks / b.total * 100) : 0),
        denyRate: nextSparkBuckets.map(b => b.total ? (b.denies / b.total * 100) : 0),
        askRate: nextSparkBuckets.map(b => b.total ? (b.asks / b.total * 100) : 0),
        skipped: nextSparkBuckets.map(b => b.skipped),
        errors: nextSparkBuckets.map(b => b.errors),
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
    const nextEventsByType = events.reduce((acc: Record<EventName, number>, e: HookEvent) => {
      acc[e.event_name] = (acc[e.event_name] || 0) + 1;
      return acc;
    }, {} as Record<EventName, number>);

    const nextEventsByTypeAndPlatform = events.reduce((acc: Record<EventName, Partial<Record<Platform, number>>>, e: HookEvent) => {
      const platformCounts = acc[e.event_name] ?? {};
      platformCounts[e.platform] = (platformCounts[e.platform] ?? 0) + 1;
      acc[e.event_name] = platformCounts;
      return acc;
    }, {} as Record<EventName, Partial<Record<Platform, number>>>);

    const tsBucketSize = windowMs <= 86400000 ? 3600000 : 86400000;
    const timeSeriesBuckets = new Map<string, Record<Decision, number>>();
    for (const r of results) {
      const t = Math.floor(new Date(r.timestamp).getTime() / tsBucketSize) * tsBucketSize;
      const key = new Date(t).toISOString();
      if (!timeSeriesBuckets.has(key)) {
        timeSeriesBuckets.set(key, { allow: 0, deny: 0, block: 0, ask: 0, context: 0, warn: 0, info: 0 });
      }
      timeSeriesBuckets.get(key)![resolveDecision(r.findings)]++;
    }

    const dupRules = ["repeated-code-block", "duplicate-call-sequence", "semantic-clone"];

    return {
      eventsByType: nextEventsByType,
      eventsByTypeAndPlatform: nextEventsByTypeAndPlatform,
      timeSeries: Array.from(timeSeriesBuckets.entries())
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([time, counts]) => ({ time, ...counts })),
      topRules: summarizeTopRules(rules),
      duplicationByRule: dupRules.map(id => ({
        rule_id: id,
        count: rules.filter((f: RuleFinding) => f.rule_id === id).length,
      })),
    };
  }, [events, results, rules, windowMs]);

  const sessions = useMemo(() => {
    const sessionMap = new Map<string, {
      platform: Platform;
      events: HookEvent[];
      findings: RuleFinding[];
      results: HookResult[];
      subprocesses: SubprocessRun[];
    }>();

    for (const e of events) {
      if (!sessionMap.has(e.session_id)) {
        sessionMap.set(e.session_id, { platform: e.platform, events: [], findings: [], results: [], subprocesses: [] });
      }
      sessionMap.get(e.session_id)!.events.push(e);
    }
    for (const r of rules) sessionMap.get(r.session_id)?.findings.push(r);
    for (const r of results) sessionMap.get(r.session_id)?.results.push(r);
    for (const s of subprocesses) sessionMap.get(s.session_id)?.subprocesses.push(s);

    return Array.from(sessionMap.entries()).map(([id, data]) => {
      const tools = [...new Set(data.events.map(e => e.tool_name).filter(Boolean))];
      const languages = [...new Set(data.events.flatMap(e => e.languages ?? []))];
      const pathCount = new Set(data.events.flatMap(e => e.candidate_paths ?? [])).size;
      const outcomes = data.results.flatMap((r: HookResult) => r.findings.map((f: { decision?: Decision | null }) => f.decision ?? "context"));
      const finalOutcome: Decision = outcomes.includes("block") ? "block"
        : outcomes.includes("deny") ? "deny"
        : outcomes.includes("ask") ? "ask"
        : "allow";
      const timestamps = data.events.map(e => new Date(e.timestamp).getTime());
      const duration = timestamps.length > 1 ? Math.max(...timestamps) - Math.min(...timestamps) : 0;

      return {
        id,
        platform: data.platform,
        eventCount: data.events.length,
        tools,
        languages,
        pathCount,
        finalOutcome,
        duration,
        events: data.events,
        findings: data.findings,
        results: data.results,
        subprocesses: data.subprocesses,
      };
    }).sort((a, b) => b.eventCount - a.eventCount);
  }, [events, results, rules, subprocesses]);

  const { asyncPassCount, asyncFailCount, asyncByCommand, hottestRepos, fireCounts } = useMemo<{
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
    hottestRepos: Array<{ repo: string; count: number }>;
    fireCounts: Map<string, number>;
  }>(() => {
    const nextAsyncPassCount = subprocesses.filter((s: SubprocessRun) => s.returncode === 0).length;
    const nextAsyncFailCount = subprocesses.filter((s: SubprocessRun) => s.returncode !== 0).length;
    const commands = [...new Set(subprocesses.map((s: SubprocessRun) => s.command))].sort();
    const nextAsyncByCommand = commands.reduce((acc, cmd) => {
      const matching = subprocesses.filter((s: SubprocessRun) => s.command === cmd);
      if (matching.length > 0) {
        acc.push({
          command: cmd,
          total: matching.length,
          pass: matching.filter((s: SubprocessRun) => s.returncode === 0).length,
          fail: matching.filter((s: SubprocessRun) => s.returncode !== 0).length,
          medianRuntime: median(matching.map((s: SubprocessRun) => s.duration_ms)),
          failures: matching.filter((s: SubprocessRun) => s.returncode !== 0).map((s: SubprocessRun) => s.stderr).slice(0, 3),
        });
      }
      return acc;
    }, [] as Array<{ command: string; total: number; pass: number; fail: number; medianRuntime: number; failures: string[] }>);

    const repoCounts = events.reduce((acc: Record<string, number>, e: HookEvent) => {
      for (const p of (e.candidate_paths ?? [])) {
        const segments = p.split("/").filter(Boolean);
        const repo = segments.length >= 3 && segments[0] === "home" ? segments[2] : (segments[0] || p);
        acc[repo] = (acc[repo] || 0) + 1;
      }
      return acc;
    }, {} as Record<string, number>);

    const nextFireCounts = new Map<string, number>();
    for (const r of rawData.rules) nextFireCounts.set(r.rule_id, (nextFireCounts.get(r.rule_id) ?? 0) + 1);

    return {
      asyncPassCount: nextAsyncPassCount,
      asyncFailCount: nextAsyncFailCount,
      asyncByCommand: nextAsyncByCommand,
      hottestRepos: (Object.entries(repoCounts) as Array<[string, number]>)
        .sort(([, a], [, b]) => b - a)
        .slice(0, 10)
        .map(([repo, count]) => ({ repo, count })),
      fireCounts: nextFireCounts,
    };
  }, [events, rawData.rules, subprocesses]);

  const operationalContext = useMemo<OperationalContext>(() => {
    const traceRecords: TraceMetadata[] = results.length > 0 ? results : [...events, ...rules];
    const blockingResults = results.filter((r: HookResult) => {
      const decision = traceDecision(r);
      return decision === "block" || decision === "deny";
    });

    const sessionDecisions = new Map<string, Decision[]>();
    for (const result of [...results].sort((a, b) => a.timestamp.localeCompare(b.timestamp))) {
      if (!sessionDecisions.has(result.session_id)) sessionDecisions.set(result.session_id, []);
      sessionDecisions.get(result.session_id)!.push(traceDecision(result));
    }
    let blockedSessions = 0;
    let resolvedBlockedSessions = 0;
    for (const decisions of sessionDecisions.values()) {
      const firstBlockIdx = decisions.findIndex(d => d === "block" || d === "deny");
      if (firstBlockIdx === -1) continue;
      blockedSessions++;
      if (decisions.slice(firstBlockIdx + 1).some(d => d === "allow" || d === "context" || d === "warn" || d === "info")) {
        resolvedBlockedSessions++;
      }
    }

    const denialCounts = new Map<string, number>();
    for (const result of blockingResults) {
      const ruleIds = result.findings
        .filter(f => f.decision === "block" || f.decision === "deny")
        .map(f => f.rule_id || "unknown-rule");
      for (const ruleId of ruleIds.length > 0 ? ruleIds : ["unknown-rule"]) {
        const key = `${result.session_id.slice(0, 8)} · ${ruleId}`;
        denialCounts.set(key, (denialCounts.get(key) ?? 0) + 1);
      }
    }

    const sessionPathCounts = new Map<string, number>();
    for (const event of events) {
      sessionPathCounts.set(
        event.session_id,
        (sessionPathCounts.get(event.session_id) ?? 0) + (event.candidate_paths ?? []).length
      );
    }

    return {
      platformCapabilities: topCounts(traceRecords.map(r => r.platform_capability)),
      enforcementModes: topCounts(traceRecords.map(r => r.enforcement_mode)),
      degradedReasons: topCounts(traceRecords.map(r => r.degraded_reason).filter(Boolean), 5),
      repoRoots: topCounts(traceRecords.map(r => shortPath(r.resolved_repo_root)), 5),
      pathlessResults: results.filter((r: HookResult) => (sessionPathCounts.get(r.session_id) ?? 0) === 0).length,
      repeatedDenials: Array.from(denialCounts.entries())
        .filter(([, count]) => count > 1)
        .sort(([, a], [, b]) => b - a)
        .slice(0, 5)
        .map(([label, count]) => ({ label, count })),
      resolutionRate: blockedSessions > 0 ? (resolvedBlockedSessions / blockedSessions) * 100 : null,
      blockedSessions,
      resolvedBlockedSessions,
    };
  }, [events, results, rules]);

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
      warning = `Live snapshot was truncated for browser safety: ${Object.entries(sourceMeta.snapshotTruncated).map(([key, count]) => `${key} +${count}`).join(", ")}.`;
    } else if (windowRecordCount === 0 && sourceMeta.latestDataAt && sourceMeta.latestDataAt < windowStartAt) {
      warning = `No accepted trace records in the selected ${filters.timeWindow} window; newest dataset record is ${sourceMeta.latestDataAt}.`;
    } else if (timeResults.length === 0 && latestByCategory.results && latestByCategory.results < windowStartAt) {
      warning = `No result records in the selected ${filters.timeWindow} window; newest result record is ${latestByCategory.results}.`;
    } else if (isStreaming && sourceMeta.acceptedStreamRecords === 0 && windowRecordCount === 0) {
      warning = "LIVE transport is connected, but no trace records have been accepted from the stream yet.";
    } else if (sourceMeta.rejectedStreamRecords > 0) {
      warning = `${sourceMeta.rejectedStreamRecords} streamed record${sourceMeta.rejectedStreamRecords === 1 ? "" : "s"} failed dashboard schema validation.`;
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

  return useMemo(() => ({
    unfilteredEvents: timeEvents,
    unfilteredRules: timeRules,
    events,
    rules,
    results,
    subprocesses,
    posture: { totalInvocations, blockRate, denyRate, askRate, skippedCount, errorCount, decisionCounts, sparklines },
    sourceStatus,
    eventsByType,
    eventsByTypeAndPlatform,
    timeSeries,
    topRules,
    duplicationByRule,
    sessions,
    async: { passCount: asyncPassCount, failCount: asyncFailCount, byCommand: asyncByCommand },
    drift: { config: mockConfig, hottestRepos, operationalContext },
    fireCounts,
  }), [
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
    hottestRepos,
    operationalContext,
    results,
    rules,
    sessions,
    skippedCount,
    sourceStatus,
    sparklines,
    subprocesses,
    timeEvents,
    timeRules,
    timeSeries,
    topRules,
    totalInvocations,
  ]);
}

function median(arr: number[]): number {
  if (arr.length === 0) return 0;
  const sorted = [...arr].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}
