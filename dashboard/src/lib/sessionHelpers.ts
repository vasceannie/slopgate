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

export interface SessionData {
	id: string;
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
		const matchingEvents = session.events.filter(
			(e) => e.tool_name === finding.tool_name && e.candidate_paths?.length > 0,
		);
		if (matchingEvents.length > 0) {
			const findingTime = new Date(finding.timestamp || "").getTime();
			let bestEvent = matchingEvents[0];
			let minDiff = Number.POSITIVE_INFINITY;
			for (const e of matchingEvents) {
				const diff = Math.abs(new Date(e.timestamp).getTime() - findingTime);
				if (diff < minDiff) {
					minDiff = diff;
					bestEvent = e;
				}
			}
			if (bestEvent.candidate_paths) {
				paths.push(...bestEvent.candidate_paths);
			}
		}
	}

	return [...new Set(paths)].filter(Boolean);
}

/**
 * Returns the primary outcome cause for a session, prioritizing blocking/denying rules,
 * then advisory rules, and falling back to Clean allow.
 */
export function primarySessionCause(session: SessionData) {
	const allFindings: Array<{
		ruleId: string;
		severity: Severity;
		decision: Decision;
		message: string | null;
		timestamp: string;
		toolName?: string;
		eventName?: string;
		paths: string[];
	}> = [];

	// 1. Gather from session.findings
	for (const f of session.findings) {
		const decision = f.decision || "context";
		allFindings.push({
			ruleId: f.rule_id,
			severity: f.severity,
			decision,
			message: f.message,
			timestamp: f.timestamp,
			toolName: f.tool_name,
			eventName: f.event_name,
			paths: getPathsForFinding(f, session),
		});
	}

	// 2. Gather from session.results findings
	for (const r of session.results) {
		const findingsList = r.findings || [];
		for (const f of findingsList) {
			const decision = f.decision || "context";
			allFindings.push({
				ruleId: f.rule_id,
				severity: f.severity,
				decision,
				message: f.message,
				timestamp: r.timestamp,
				toolName: r.tool_name,
				eventName: r.event_name,
				paths: getPathsForFinding(
					{ ...f, timestamp: r.timestamp, tool_name: r.tool_name },
					session,
				),
			});
		}
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

	const blockingFindings = allFindings.filter(
		(f) => f.decision === "block" || f.decision === "deny",
	);
	const advisoryFindings = allFindings.filter(
		(f) =>
			f.decision !== "block" &&
			f.decision !== "deny" &&
			f.decision !== "allow",
	);

	if (blockingFindings.length > 0) {
		blockingFindings.sort((a, b) => {
			const decDiff =
				DECISION_PRIORITY[b.decision] - DECISION_PRIORITY[a.decision];
			if (decDiff !== 0) return decDiff;
			const sevDiff =
				SEVERITY_PRIORITY[b.severity] - SEVERITY_PRIORITY[a.severity];
			if (sevDiff !== 0) return sevDiff;
			return b.timestamp.localeCompare(a.timestamp);
		});
		const primary = blockingFindings[0];
		return {
			decision: primary.decision,
			ruleId: primary.ruleId,
			severity: primary.severity,
			message: primary.message,
			eventName: primary.eventName,
			toolName: primary.toolName,
			path: primary.paths[0] || undefined,
			paths: primary.paths,
		};
	}

	if (advisoryFindings.length > 0) {
		advisoryFindings.sort((a, b) => {
			const decDiff =
				DECISION_PRIORITY[b.decision] - DECISION_PRIORITY[a.decision];
			if (decDiff !== 0) return decDiff;
			const sevDiff =
				SEVERITY_PRIORITY[b.severity] - SEVERITY_PRIORITY[a.severity];
			if (sevDiff !== 0) return sevDiff;
			return b.timestamp.localeCompare(a.timestamp);
		});
		const primary = advisoryFindings[0];
		return {
			decision: primary.decision,
			ruleId: primary.ruleId,
			severity: primary.severity,
			message: primary.message,
			eventName: primary.eventName,
			toolName: primary.toolName,
			path: primary.paths[0] || undefined,
			paths: primary.paths,
		};
	}

	// Fallback to error check if outcome is block/deny but no finding matched
	if (session.finalOutcome === "block" || session.finalOutcome === "deny") {
		const errorResult = session.results.find(
			(r) => r.errors && r.errors.length > 0,
		);
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
	const eventsWithTool = [...session.events]
		.filter((e) => e.tool_name)
		.sort((a, b) => a.timestamp.localeCompare(b.timestamp));
	const lastTool =
		eventsWithTool.length > 0
			? eventsWithTool[eventsWithTool.length - 1].tool_name
			: null;
	const uniqueTools = new Set(
		session.events.map((e) => e.tool_name).filter(Boolean),
	);
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
export function initialTimelineSelection(
	entries: TimelineEntry[],
): string | null {
	if (entries.length === 0) return null;

	const blockDeny = entries.find(
		(e) => e.decision === "block" || e.decision === "deny",
	);
	if (blockDeny) return blockDeny.id;

	const withFindings = entries.find(
		(e) => (e.findingCount ?? 0) > 0 || e.type === "finding",
	);
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
		primaryEvidenceLabel = entry.findingCount
			? `${entry.findingCount} finding${entry.findingCount === 1 ? "" : "s"}`
			: "No findings";
		if (entry.errorCount) {
			primaryEvidenceLabel += `, ${entry.errorCount} error${
				entry.errorCount === 1 ? "" : "s"
			}`;
		}
	} else if (entry.type === "result") {
		title = `Result: ${entry.decision}`;
		subtitle = entry.detail;
		primaryEvidenceLabel = entry.findingCount
			? `${entry.findingCount} finding${entry.findingCount === 1 ? "" : "s"}`
			: "";
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
export function correlationStatus(
	entry: TimelineEntry,
): "matched" | "nearby" | "unmatched" | "historical-missing-input" {
	if (entry.type === "hook" || entry.correlation === "matched") {
		return "matched";
	}

	const isToolEvent =
		entry.eventName === "PreToolUse" || entry.eventName === "PostToolUse";
	const hasBody = Boolean(
		entry.command ||
			entry.tool_output ||
			entry.patch_text ||
			entry.edit_before ||
			entry.edit_after ||
			entry.tool_input_json,
	);

	if (entry.toolName && isToolEvent && !hasBody) {
		return "historical-missing-input";
	}

	if (entry.type === "result" || entry.correlation === "nearby") {
		const hasCorrelatedData = Boolean(
			entry.candidate_paths?.length ||
				entry.tool_context?.length ||
				entry.url_context?.length ||
				entry.model ||
				entry.provider,
		);
		return hasCorrelatedData ? "nearby" : "unmatched";
	}

	return "unmatched";
}
