import type {
  Decision,
  HookEvent,
  HookResult,
  LineageConfidence,
  LineageRole,
  Platform,
  PlatformSource,
  RuleFinding,
  Severity,
  SubprocessRun,
} from "@/types/slopgate";

export interface NativeSessionIds {
  opencode?: string | null;
  codex?: string | null;
  claude?: string | null;
}

export interface SessionData {
  id: string;
  title?: string | null;
  titleSource?: string | null;
  sessionIdentitySource?: string | null;
  secondaryIds?: string[];
  nativeSessionIds?: NativeSessionIds;
  platform: Platform;
  platforms?: Platform[];
  parentSessionId?: string | null;
  rootSessionId?: string | null;
  originPlatform?: Platform | null;
  originSessionId?: string | null;
  platformSource?: PlatformSource | null;
  subagentType?: string | null;
  spawnDescription?: string | null;
  lineageRole?: LineageRole | null;
  lineageConfidence?: LineageConfidence;
  rawSessionIds?: string[];
  childSessions?: SessionData[];
  mirrorSessions?: SessionData[];
  eventCount: number;
  tools: string[];
  languages: string[];
  pathCount: number;
  finalOutcome: Decision;
  duration: number;
  events: HookEvent[];
  findings: RuleFinding[];
  results: HookResult[];
  subprocesses: SubprocessRun[];
}

export interface SessionGroup {
  id: string;
  primarySession: SessionData;
  childSessions: SessionData[];
  mirrorSessions: SessionData[];
  rawSessionIds: string[];
  platforms: Platform[];
  lineageConfidence: LineageConfidence;
}

export type TimelineFinding = {
  id: string;
  ruleId: string;
  severity: Severity;
  decision: Decision | null;
  message: string | null;
  additionalContext?: string | null;
};

export type TimelineEntry = {
  id: string;
  time: string;
  type: "event" | "finding" | "result" | "subprocess" | "hook";
  label: string;
  detail: string;
  sessionId: string;
  sourceSessionId?: string;
  sourceLineageRole?: LineageRole | null;
  platform?: string;
  eventName?: string;
  toolName?: string;
  eventTime?: string;
  resultTime?: string;
  decision?: Decision;
  resultLabel?: string;
  resultDetail?: string;
  findingCount?: number;
  errorCount?: number;
  flagItemType: "event" | "finding" | "result" | "session";
  flagItemId: string;
  flagLabel: string;
  model?: string | null;
  provider?: string | null;
  command?: string | null;
  tool_output?: string | null;
  candidate_paths?: string[];
  tool_context?: string[];
  url_context?: string[];
  patch_text?: string | null;
  edit_before?: string | null;
  edit_after?: string | null;
  tool_input_json?: string | null;
  findings?: TimelineFinding[];
  correlation?: "matched" | "nearby" | "unmatched" | "historical-missing-input";
};

interface FindingLike {
  rule_id: string;
  severity: Severity;
  decision: Decision | null;
  message: string | null;
  timestamp?: string;
  tool_name?: string;
  event_name?: string;
  tool_input?: Record<string, unknown> | null;
  metadata?: Record<string, unknown>;
}

interface CauseCandidate {
  ruleId: string;
  severity: Severity;
  decision: Decision;
  message: string | null;
  timestamp: string;
  toolName?: string;
  eventName?: string;
  finding: FindingLike;
}

const DECISION_PRIORITY: Record<Decision, number> = {
  block: 6,
  deny: 5,
  ask: 4,
  warn: 3,
  context: 2,
  info: 1,
  allow: 0,
};

const SEVERITY_PRIORITY: Record<Severity, number> = {
  CRITICAL: 4,
  HIGH: 3,
  MEDIUM: 2,
  LOW: 1,
};

function isBlockingDecision(decision: Decision): boolean {
  return decision === "block" || decision === "deny";
}

function isAdvisoryDecision(decision: Decision): boolean {
  return decision !== "block" && decision !== "deny" && decision !== "allow";
}

function isBetterCauseCandidate(candidate: CauseCandidate, current: CauseCandidate | null): boolean {
  if (!current) return true;
  const decisionDiff = DECISION_PRIORITY[candidate.decision] - DECISION_PRIORITY[current.decision];
  if (decisionDiff !== 0) return decisionDiff > 0;
  const severityDiff = SEVERITY_PRIORITY[candidate.severity] - SEVERITY_PRIORITY[current.severity];
  if (severityDiff !== 0) return severityDiff > 0;
  return candidate.timestamp > current.timestamp;
}

/**
 * Extracts candidate paths associated with a finding by checking its tool input
 * or correlating with matching session events close to its timestamp.
 */
function getPathsForFinding(finding: FindingLike, session: SessionData): string[] {
  const paths: string[] = [];

  // 1. Check tool_input in finding
  const toolInput = finding.tool_input || (finding.metadata?.tool_input as Record<string, unknown> | undefined);
  if (toolInput) {
    const filePath = toolInput.file_path || toolInput.filePath || toolInput.path;
    if (typeof filePath === "string" && filePath.trim()) {
      paths.push(filePath.trim());
    }
  }

  // 2. Correlate with session events using tool_name and closest timestamp
  if (finding.tool_name) {
    const findingTime = new Date(finding.timestamp || "").getTime();
    const hasFindingTime = Number.isFinite(findingTime);
    let bestEvent: HookEvent | null = null;
    let minDiff = Number.POSITIVE_INFINITY;
    for (const event of session.events) {
      if (event.tool_name !== finding.tool_name || !event.candidate_paths?.length) {
        continue;
      }
      if (!hasFindingTime) {
        bestEvent = event;
        break;
      }
      const eventTime = new Date(event.timestamp).getTime();
      if (!Number.isFinite(eventTime)) continue;
      const diff = Math.abs(eventTime - findingTime);
      if (diff < minDiff) {
        minDiff = diff;
        bestEvent = event;
      }
    }
    if (bestEvent?.candidate_paths) {
      paths.push(...bestEvent.candidate_paths);
    }
  }

  return [...new Set(paths)].filter(Boolean);
}

/**
 * Returns the primary outcome cause for a session, prioritizing blocking/denying rules,
 * then advisory rules, and falling back to Clean allow.
 */
export function primarySessionCause(session: SessionData) {
  let bestBlocking: CauseCandidate | null = null;
  let bestAdvisory: CauseCandidate | null = null;
  const considerFinding = (finding: FindingLike) => {
    const decision = finding.decision || "context";
    const candidate: CauseCandidate = {
      ruleId: finding.rule_id,
      severity: finding.severity,
      decision,
      message: finding.message,
      timestamp: finding.timestamp || "",
      toolName: finding.tool_name,
      eventName: finding.event_name,
      finding,
    };
    if (isBlockingDecision(decision)) {
      if (isBetterCauseCandidate(candidate, bestBlocking)) {
        bestBlocking = candidate;
      }
      return;
    }
    if (isAdvisoryDecision(decision)) {
      if (isBetterCauseCandidate(candidate, bestAdvisory)) {
        bestAdvisory = candidate;
      }
    }
  };

  // 1. Gather from session.findings
  for (const f of session.findings) {
    considerFinding(f);
  }

  // 2. Gather from session.results findings
  for (const r of session.results) {
    const findingsList = r.findings || [];
    for (const f of findingsList) {
      considerFinding({
        ...f,
        timestamp: r.timestamp,
        tool_name: r.tool_name,
        event_name: r.event_name,
      });
    }
  }

  const primary = bestBlocking ?? bestAdvisory;
  if (primary) {
    const paths = getPathsForFinding(primary.finding, session);
    return {
      decision: primary.decision,
      ruleId: primary.ruleId,
      severity: primary.severity,
      message: primary.message,
      eventName: primary.eventName,
      toolName: primary.toolName,
      path: paths[0] || undefined,
      paths,
    };
  }

  // Fallback to error check if outcome is block/deny but no finding matched
  if (session.finalOutcome === "block" || session.finalOutcome === "deny") {
    const errorResult = session.results.find((r) => r.errors && r.errors.length > 0);
    if (errorResult) {
      return {
        decision: session.finalOutcome,
        message: errorResult.errors?.join(", ") || "Unknown session error",
        eventName: errorResult.event_name,
        toolName: errorResult.tool_name,
        paths: [],
      };
    }
  }

  return {
    decision: "allow" as Decision,
    message: "Clean allow",
    paths: [],
  };
}

/**
 * Returns a summary of agent activity in a session: last tool used, tool counts, event/path counts.
 */
export function sessionActivitySummary(session: SessionData) {
  let lastTool: string | null = null;
  let lastToolTimestamp = "";
  const uniqueTools = new Set<string>();
  for (const event of session.events) {
    if (!event.tool_name) continue;
    uniqueTools.add(event.tool_name);
    if (!lastTool || event.timestamp >= lastToolTimestamp) {
      lastTool = event.tool_name;
      lastToolTimestamp = event.timestamp;
    }
  }
  return {
    lastTool,
    toolCount: uniqueTools.size,
    eventCount: session.events.length,
    pathCount: session.pathCount,
  };
}

/**
 * Selects the best initial timeline row to expand by default.
 */
export function initialTimelineSelection(entries: TimelineEntry[]): string | null {
  if (entries.length === 0) return null;

  const blockDeny = entries.find((e) => e.decision === "block" || e.decision === "deny");
  if (blockDeny) return blockDeny.id;

  const withFindings = entries.find((e) => (e.findingCount ?? 0) > 0 || e.type === "finding");
  if (withFindings) return withFindings.id;

  const newestHook = entries.find((e) => e.type === "hook");
  if (newestHook) return newestHook.id;

  return entries[0].id;
}

/**
 * Returns user-friendly formatting details for a timeline entry.
 */
export function timelineRowSummary(entry: TimelineEntry) {
  let title = entry.label;
  let subtitle = entry.detail;
  const decisionLabel = entry.decision || "n/a";
  let primaryEvidenceLabel = "";

  if (entry.type === "hook") {
    title = `${entry.eventName} (${entry.toolName || "lifecycle"})`;
    subtitle = entry.detail;
    primaryEvidenceLabel = entry.findingCount ? `${entry.findingCount} finding${entry.findingCount === 1 ? "" : "s"}` : "No findings";
    if (entry.errorCount) {
      primaryEvidenceLabel += `, ${entry.errorCount} error${entry.errorCount === 1 ? "" : "s"}`;
    }
  } else if (entry.type === "result") {
    title = `Result: ${entry.decision}`;
    subtitle = entry.detail;
    primaryEvidenceLabel = entry.findingCount ? `${entry.findingCount} finding${entry.findingCount === 1 ? "" : "s"}` : "";
  } else if (entry.type === "finding") {
    title = entry.label;
    subtitle = entry.detail;
    primaryEvidenceLabel = entry.decision || "";
  } else if (entry.type === "subprocess") {
    title = entry.label;
    subtitle = entry.detail;
    primaryEvidenceLabel = entry.decision || "";
  }

  return {
    title,
    subtitle,
    decisionLabel,
    primaryEvidenceLabel,
  };
}

/**
 * Checks correlation status of a timeline entry.
 */
export function correlationStatus(entry: TimelineEntry): "matched" | "nearby" | "unmatched" | "historical-missing-input" {
  if (entry.type === "hook" || entry.correlation === "matched") {
    return "matched";
  }

  const isToolEvent = entry.eventName === "PreToolUse" || entry.eventName === "PostToolUse";
  const hasBody = Boolean(
    entry.command || entry.tool_output || entry.patch_text || entry.edit_before || entry.edit_after || entry.tool_input_json,
  );

  if (entry.toolName && isToolEvent && !hasBody) {
    return "historical-missing-input";
  }

  if (entry.type === "result" || entry.correlation === "nearby") {
    const hasCorrelatedData = Boolean(
      entry.candidate_paths?.length || entry.tool_context?.length || entry.url_context?.length || entry.model || entry.provider,
    );
    return hasCorrelatedData ? "nearby" : "unmatched";
  }

  return "unmatched";
}
