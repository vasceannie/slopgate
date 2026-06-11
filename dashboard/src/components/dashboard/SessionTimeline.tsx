import { memo, type ReactNode, useMemo, useState } from "react";
import { resolveDecision } from "@/hooks/useTraceData";
import { DECISION_DOT_STYLE } from "@/lib/chartTheme";
import { cn } from "@/lib/utils";
import type {
	Decision,
	HookEvent,
	HookResult,
	Severity,
} from "@/types/slopgate";
import { FlagButton } from "./FlagButton";
import type { SessionData } from "./SessionExplorer";

const PAGE_SIZE = 50;
const TOOL_DRILLDOWN_CORRELATION_WINDOW_MS = 120_000;

type DetailToggle = "findings" | "errors";

const DETAIL_TOGGLE_LABELS: Record<DetailToggle, string> = {
	findings: "Findings",
	errors: "Errors",
};

const DETAIL_TOGGLES: DetailToggle[] = ["findings", "errors"];

type TimelineEntry = {
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
};

type TimelineFinding = {
	id: string;
	ruleId: string;
	severity: Severity;
	decision: Decision | null;
	message: string | null;
	additionalContext?: string | null;
};

type EventMatch = {
	event: HookEvent;
	index: number;
};

type DrilldownFields = Pick<
	TimelineEntry,
	| "model"
	| "provider"
	| "command"
	| "tool_output"
	| "candidate_paths"
	| "tool_context"
	| "url_context"
	| "patch_text"
	| "edit_before"
	| "edit_after"
	| "tool_input_json"
>;

type ToolInputDetails = {
	command?: string | null;
	patch_text?: string | null;
	edit_before?: string | null;
	edit_after?: string | null;
	tool_output?: string | null;
	tool_input_json?: string | null;
	candidate_paths?: string[];
	url_context?: string[];
	tool_context?: string[];
};

type ResultFinding = HookResult["findings"][number];

type FormattedHookOutput = {
	label: string;
	value: string;
	variant: "context" | "decision" | "metadata" | "raw";
};

const FILE_CONTEXT_PATTERN =
	/(^\.?\.?\/|\/|\\|\.(py|ts|tsx|js|jsx|json|md|toml|ya?ml|sh|css|html|tool)$|^(src|tests?|dashboard|bundle|docs|logs|scripts)$)/i;
const TOOL_EXPRESSION_PATTERN =
	/[{}(),]|\\[.dws]|\b(button|document|window|String)\b/;
const URL_CONTEXT_PATTERN = /^(https?:)?\/\//i;
const LOW_VALUE_CONTEXT_PATTERN =
	/^[{,\s]+|\b(textContent|className|length)\b|['")]+\./;

function textField(
	record: Record<string, unknown> | null,
	fields: string[],
): string | null {
	for (const field of fields) {
		const value = record?.[field];
		if (typeof value === "string" && value.trim()) return value;
	}
	return null;
}

function isFileContext(value: string): boolean {
	const trimmed = value.trim();
	return Boolean(
		trimmed &&
			!URL_CONTEXT_PATTERN.test(trimmed) &&
			!TOOL_EXPRESSION_PATTERN.test(trimmed) &&
			FILE_CONTEXT_PATTERN.test(trimmed),
	);
}

function isUrlContext(value: string): boolean {
	return URL_CONTEXT_PATTERN.test(value.trim());
}

function isUsefulToolContext(value: string): boolean {
	const trimmed = value.trim();
	return Boolean(
		trimmed &&
			!isFileContext(trimmed) &&
			!isUrlContext(trimmed) &&
			!LOW_VALUE_CONTEXT_PATTERN.test(trimmed),
	);
}

function splitCandidateContext(candidatePaths: string[] | undefined): {
	candidate_paths?: string[];
	tool_context?: string[];
	url_context?: string[];
} {
	if (!candidatePaths?.length) return {};
	const filePaths = candidatePaths.filter(isFileContext);
	const urlContext = candidatePaths.filter(isUrlContext);
	const toolContext = candidatePaths.filter(isUsefulToolContext);
	return {
		candidate_paths: filePaths.length > 0 ? filePaths : undefined,
		tool_context: toolContext.length > 0 ? toolContext : undefined,
		url_context: urlContext.length > 0 ? urlContext : undefined,
	};
}

function outputRecord(value: unknown): Record<string, unknown> | null {
	if (typeof value !== "object" || value === null || Array.isArray(value)) {
		return null;
	}
	return Object.fromEntries(Object.entries(value));
}

function hasDirectToolInputFields(record: Record<string, unknown>): boolean {
	return [
		"command",
		"cmd",
		"code",
		"patchText",
		"patch",
		"diff",
		"old_string",
		"oldString",
		"new_string",
		"newString",
		"file_path",
		"filePath",
		"path",
	].some((key) => record[key] !== undefined);
}

function textFromUnknown(value: unknown): string | null {
	return typeof value === "string" && value.trim() ? value : null;
}

function commandFromOutput(
	output: Record<string, unknown> | null,
): string | null {
	const direct = textField(output, ["command", "cmd"]);
	if (direct) return direct;

	const nestedRecords = [
		outputRecord(output?.input),
		outputRecord(output?.tool_input),
		outputRecord(output?.toolInput),
		outputRecord(output?.tool_args),
		outputRecord(output?.args),
		outputRecord(output?.arguments),
	];
	for (const record of nestedRecords) {
		const nested = textField(record, ["command", "cmd", "code"]);
		if (nested) return nested;
	}

	return null;
}

function toolInputFromOutput(
	output: Record<string, unknown> | null,
): Record<string, unknown> | null {
	if (!output) return null;
	const nested =
		outputRecord(output.input) ??
		outputRecord(output.tool_input) ??
		outputRecord(output.toolInput) ??
		outputRecord(output.tool_args) ??
		outputRecord(output.args) ??
		outputRecord(output.arguments);
	if (nested) return nested;
	return hasDirectToolInputFields(output) ? output : null;
}

function candidatePathsFromInput(
	input: Record<string, unknown> | null,
): string[] | undefined {
	if (!input) return undefined;
	const candidates = [
		input.file_path,
		input.filePath,
		input.path,
		input.url,
		input.uri,
	].filter(
		(value): value is string =>
			typeof value === "string" && Boolean(value.trim()),
	);
	return candidates.length > 0 ? candidates : undefined;
}

function nestedInputRecords(
	input: Record<string, unknown> | null,
): Record<string, unknown>[] {
	if (!input) return [];
	return [
		input,
		outputRecord(input.input),
		outputRecord(input.tool_input),
		outputRecord(input.toolInput),
		outputRecord(input.tool_args),
		outputRecord(input.args),
		outputRecord(input.arguments),
	].filter((record): record is Record<string, unknown> => record !== null);
}

function nonEmptyObject(value: Record<string, unknown> | null): boolean {
	return value !== null && Object.keys(value).length > 0;
}

function jsonFromRecord(value: Record<string, unknown> | null): string | null {
	if (!nonEmptyObject(value)) return null;
	return JSON.stringify(value, null, 2);
}

function jsonRecordFromText(value: string): Record<string, unknown> | null {
	try {
		return outputRecord(JSON.parse(value));
	} catch {
		return null;
	}
}

function textFromRecordKey(
	record: Record<string, unknown>,
	key: string,
): string | null {
	const value = record[key];
	if (typeof value === "string" && value.trim()) return value;
	if (typeof value === "boolean" || typeof value === "number")
		return String(value);
	return null;
}

function splitHookMessage(value: string): string {
	return value
		.split(/\n(?=\[[A-Z0-9-]+\s*\|)/)
		.map((line) => line.trim())
		.filter(Boolean)
		.join("\n\n");
}

function appendHookOutputSection(
	sections: FormattedHookOutput[],
	record: Record<string, unknown>,
	keys: string[],
	label: string,
	variant: FormattedHookOutput["variant"],
) {
	const value = keys
		.map((key) => textFromRecordKey(record, key))
		.find((candidate): candidate is string => candidate !== null);
	if (!value) return;
	sections.push({ label, value: splitHookMessage(value), variant });
}

function formattedHookOutputSections(value: string): FormattedHookOutput[] {
	const root = jsonRecordFromText(value);
	if (!root) return [{ label: "Raw output", value, variant: "raw" }];
	const hookSpecific =
		outputRecord(root.hookSpecificOutput) ??
		outputRecord(root.hook_specific_output);
	const records = hookSpecific ? [root, hookSpecific] : [root];
	const sections: FormattedHookOutput[] = [];

	for (const record of records) {
		appendHookOutputSection(
			sections,
			record,
			["hookEventName", "hook_event_name"],
			"Hook event",
			"metadata",
		);
		appendHookOutputSection(sections, record, ["action"], "Action", "metadata");
		appendHookOutputSection(
			sections,
			record,
			["decision"],
			"Decision",
			"decision",
		);
		appendHookOutputSection(
			sections,
			record,
			["permissionDecision", "permission_decision"],
			"Permission decision",
			"decision",
		);
		appendHookOutputSection(
			sections,
			record,
			["continue"],
			"Continue",
			"decision",
		);
		appendHookOutputSection(sections, record, ["reason"], "Reason", "decision");
		appendHookOutputSection(
			sections,
			record,
			["permissionDecisionReason", "permission_decision_reason"],
			"Permission reason",
			"decision",
		);
		appendHookOutputSection(
			sections,
			record,
			["stopReason", "stop_reason"],
			"Stop reason",
			"decision",
		);
		appendHookOutputSection(
			sections,
			record,
			["context"],
			"Context",
			"context",
		);
		appendHookOutputSection(
			sections,
			record,
			["additionalContext", "additional_context"],
			"Additional context",
			"context",
		);
		appendHookOutputSection(
			sections,
			record,
			["systemMessage", "system_message"],
			"System message",
			"context",
		);
		appendHookOutputSection(
			sections,
			record,
			["updatedInput", "updated_input", "updated_args"],
			"Updated input",
			"metadata",
		);
	}

	if (sections.length > 0) return sections;
	return [
		{
			label: "Raw output",
			value: JSON.stringify(root, null, 2),
			variant: "raw",
		},
	];
}

function outputSectionClass(variant: FormattedHookOutput["variant"]): string {
	if (variant === "decision")
		return "border-signal-danger/20 bg-signal-danger/5";
	if (variant === "context") return "border-signal-ask/20 bg-signal-ask/5";
	if (variant === "metadata") return "border-primary/20 bg-primary/5";
	return "border-border/20 bg-background/50";
}

function toolInputDetails(
	output: Record<string, unknown> | null,
): ToolInputDetails {
	return toolInputDetailsFromInput(toolInputFromOutput(output));
}

function toolInputDetailsFromInput(
	input: Record<string, unknown> | null,
): ToolInputDetails {
	const records = nestedInputRecords(input);
	const firstTextField = (fields: string[]) => {
		for (const record of records) {
			const value = textField(record, fields);
			if (value) return value;
		}
		return null;
	};
	const candidatePaths = records.flatMap(
		(record) => candidatePathsFromInput(record) ?? [],
	);
	const candidateContext = splitCandidateContext(
		candidatePaths.length > 0 ? candidatePaths : undefined,
	);
	return {
		command: firstTextField(["command", "cmd", "code"]),
		patch_text: firstTextField(["patchText", "patch", "diff"]),
		edit_before: firstTextField(["old_string", "oldString", "before"]),
		edit_after: firstTextField(["new_string", "newString", "after"]),
		tool_output: firstTextField(["text", "content"]),
		tool_input_json: jsonFromRecord(input),
		...candidateContext,
	};
}

function focusedEditDiff(entry: TimelineEntry): string | null {
	const before = textFromUnknown(entry.edit_before);
	const after = textFromUnknown(entry.edit_after);
	if (!before && !after) return entry.patch_text ?? null;
	return [
		"--- before",
		"+++ after",
		...(before ?? "").split("\n").map((line) => `-${line}`),
		...(after ?? "").split("\n").map((line) => `+${line}`),
	].join("\n");
}

function outputSummary(output: Record<string, unknown> | null): string | null {
	if (!output) return null;
	const stdout = textField(output, ["stdout"]);
	const stderr = textField(output, ["stderr"]);
	if (stdout || stderr) {
		return [
			stdout ? `stdout:\n${stdout}` : null,
			stderr ? `stderr:\n${stderr}` : null,
		]
			.filter((value): value is string => value !== null)
			.join("\n");
	}
	const summary = textField(output, ["summary", "message", "result", "output"]);
	if (summary) return summary;
	const keys = Object.keys(output);
	const onlyToolInput = keys.every((key) =>
		[
			"input",
			"tool_input",
			"toolInput",
			"tool_args",
			"args",
			"arguments",
		].includes(key),
	);
	if (onlyToolInput) return null;
	const text = JSON.stringify(output, null, 2);
	return text === "{}" ? null : text;
}

function toolContextLabel(entry: TimelineEntry): string {
	return entry.toolName === "Bash" ? "Command context" : "Tool context";
}

function hasDrilldown(fields: DrilldownFields): boolean {
	return Boolean(
		fields.model ||
			fields.provider ||
			fields.command ||
			fields.tool_output ||
			fields.candidate_paths?.length ||
			fields.tool_context?.length ||
			fields.url_context?.length ||
			fields.patch_text ||
			fields.edit_before ||
			fields.edit_after ||
			fields.tool_input_json,
	);
}

function hasToolCallBody(
	entry: TimelineEntry,
	diffText: string | null,
): boolean {
	return Boolean(
		entry.command ||
			entry.tool_output ||
			diffText ||
			entry.edit_before ||
			entry.edit_after ||
			entry.tool_input_json,
	);
}

function missingToolCallBodyReason(entry: TimelineEntry): string | null {
	if (!entry.toolName) return null;
	if (entry.eventName !== "PreToolUse" && entry.eventName !== "PostToolUse") {
		return null;
	}
	return "Tool call body was not captured for this trace record. Newer traces include tool input when the harness exposes it; this historical row only has paths/findings metadata.";
}

function eventDrilldown(event: {
	model?: string | null;
	provider?: string | null;
	command?: string | null;
	tool_output?: string | null;
	candidate_paths?: string[];
	tool_input?: Record<string, unknown> | null;
}): DrilldownFields {
	return mergeDrilldown(
		{
			model: event.model,
			provider: event.provider,
			command: event.command,
			tool_output: event.tool_output,
			...splitCandidateContext(event.candidate_paths),
		},
		toolInputDetailsFromInput(event.tool_input ?? null),
	);
}

function findNearbyDrilldown(
	events: Array<{
		timestamp: string;
		event_name: string;
		tool_name: string;
		model?: string | null;
		provider?: string | null;
		command?: string | null;
		tool_output?: string | null;
		candidate_paths?: string[];
		tool_input?: Record<string, unknown> | null;
	}>,
	timestamp: string,
	eventName: string,
	toolName: string,
): DrilldownFields {
	const target = Date.parse(timestamp);
	let best: DrilldownFields = {};
	let bestDistance = Number.POSITIVE_INFINITY;

	for (const event of events) {
		if (toolName && event.tool_name && event.tool_name !== toolName) continue;
		if (eventName === "PostToolUse") {
			if (
				event.event_name !== "PreToolUse" &&
				event.event_name !== "PermissionRequest"
			) {
				continue;
			}
		} else if (event.event_name !== eventName) {
			continue;
		}
		const distance = Math.abs(Date.parse(event.timestamp) - target);
		if (
			!Number.isFinite(distance) ||
			distance > TOOL_DRILLDOWN_CORRELATION_WINDOW_MS
		) {
			continue;
		}
		const fields = eventDrilldown(event);
		if (!hasDrilldown(fields) || distance >= bestDistance) continue;
		best = fields;
		bestDistance = distance;
	}

	return best;
}

function mergeDrilldown(
	primary: DrilldownFields,
	fallback: DrilldownFields,
): DrilldownFields {
	return {
		model: primary.model ?? fallback.model,
		provider: primary.provider ?? fallback.provider,
		command: primary.command ?? fallback.command,
		tool_output: primary.tool_output ?? fallback.tool_output,
		tool_input_json: primary.tool_input_json ?? fallback.tool_input_json,
		patch_text: primary.patch_text ?? fallback.patch_text,
		edit_before: primary.edit_before ?? fallback.edit_before,
		edit_after: primary.edit_after ?? fallback.edit_after,
		candidate_paths: primary.candidate_paths?.length
			? primary.candidate_paths
			: fallback.candidate_paths,
		tool_context: primary.tool_context?.length
			? primary.tool_context
			: fallback.tool_context,
		url_context: primary.url_context?.length
			? primary.url_context
			: fallback.url_context,
	};
}

function shortSessionId(sessionId: string): string {
	return sessionId.length > 16 ? `${sessionId.slice(0, 16)}…` : sessionId;
}

function formatAuditTime(timestamp: string | undefined): string {
	if (!timestamp) return "unknown";
	return new Date(timestamp).toLocaleTimeString();
}

function auditRows(entry: TimelineEntry): Array<[string, string]> {
	return [
		["Session", shortSessionId(entry.sessionId)],
		["Platform", entry.platform ?? "unknown"],
		["Event", entry.eventName ?? entry.label],
		["Tool", entry.toolName || "session lifecycle"],
		["Event time", formatAuditTime(entry.eventTime ?? entry.time)],
		["Result time", formatAuditTime(entry.resultTime)],
		["Decision", entry.decision ?? "n/a"],
		["Findings", String(entry.findingCount ?? 0)],
		["Errors", String(entry.errorCount ?? 0)],
	];
}

function toggleSetValue<T>(selected: Set<T>, value: T): Set<T> {
	const next = new Set(selected);
	if (next.has(value)) next.delete(value);
	else next.add(value);
	return next;
}

function entryHasError(entry: TimelineEntry): boolean {
	return (
		(entry.errorCount ?? 0) > 0 ||
		entry.eventName === "PostToolUseFailure" ||
		entry.decision === "deny" ||
		entry.decision === "block"
	);
}

function matchesDetailToggles(
	entry: TimelineEntry,
	detailToggles: Set<DetailToggle>,
): boolean {
	return (
		detailToggles.size === 0 ||
		(detailToggles.has("findings") && (entry.findingCount ?? 0) > 0) ||
		(detailToggles.has("errors") && entryHasError(entry))
	);
}

function matchesNestedFilters(
	entry: TimelineEntry,
	selectedEvents: Set<string>,
	selectedTools: Set<string>,
	selectedDecisions: Set<Decision>,
	detailToggles: Set<DetailToggle>,
): boolean {
	return (
		(selectedEvents.size === 0 ||
			Boolean(entry.eventName && selectedEvents.has(entry.eventName))) &&
		(selectedTools.size === 0 ||
			Boolean(entry.toolName && selectedTools.has(entry.toolName))) &&
		(selectedDecisions.size === 0 ||
			Boolean(entry.decision && selectedDecisions.has(entry.decision))) &&
		matchesDetailToggles(entry, detailToggles)
	);
}

function eventDetail(event: HookEvent): string {
	const cp = splitCandidateContext(event.candidate_paths).candidate_paths ?? [];
	const pathInfo = cp.length > 0 ? ` → ${cp.join(", ")}` : "";
	return (
		(event.tool_name ? `tool: ${event.tool_name}` : "session lifecycle") +
		pathInfo
	);
}

function resultDetail(result: HookResult): string {
	const errors = result.errors ?? [];
	return `${result.findings.length} findings, ${errors.length} errors`;
}

function timelineFindings(
	sessionId: string,
	resultIndex: number,
	findings: ResultFinding[],
): TimelineFinding[] {
	return findings.map((finding, findingIndex) => ({
		id: `${sessionId}:result-finding:${resultIndex}:${findingIndex}:${finding.rule_id}`,
		ruleId: finding.rule_id,
		severity: finding.severity,
		decision: finding.decision,
		message: finding.message,
		additionalContext: finding.additional_context,
	}));
}

function findingSummary(finding: TimelineFinding): string {
	const decision = finding.decision ?? "context";
	const message = finding.message?.trim() || "No message provided.";
	return `${finding.severity} → ${decision}: ${message}`;
}

function isDuplicateFindingEntry(
	finding: {
		timestamp: string;
		tool_name: string;
		rule_id: string;
	},
	results: HookResult[],
): boolean {
	const findingTime = Date.parse(finding.timestamp);
	return results.some((result) => {
		if (result.tool_name !== finding.tool_name) return false;
		if (!result.findings.some((item) => item.rule_id === finding.rule_id)) {
			return false;
		}
		const distance = Math.abs(Date.parse(result.timestamp) - findingTime);
		return Number.isFinite(distance) && distance <= 5000;
	});
}

function entryTypeClass(type: TimelineEntry["type"]): string {
	if (type === "event" || type === "hook")
		return "bg-muted text-muted-foreground";
	if (type === "finding") return "bg-signal-ask/10 text-signal-ask";
	if (type === "result") return "bg-primary/10 text-primary";
	return "bg-signal-warn/10 text-signal-warn";
}

function findMatchingEvent(
	events: HookEvent[],
	claimedEventIndexes: Set<number>,
	result: HookResult,
): EventMatch | null {
	const resultTime = Date.parse(result.timestamp);
	let bestMatch: EventMatch | null = null;
	let bestDistance = Number.POSITIVE_INFINITY;

	for (const [index, event] of events.entries()) {
		if (claimedEventIndexes.has(index)) continue;
		if (event.event_name !== result.event_name) continue;
		if (event.tool_name !== result.tool_name) continue;
		const distance = Math.abs(Date.parse(event.timestamp) - resultTime);
		if (!Number.isFinite(distance) || distance > 5000) continue;
		if (distance >= bestDistance) continue;
		bestMatch = { event, index };
		bestDistance = distance;
	}

	return bestMatch;
}

export const SessionTimeline = memo(function SessionTimeline({
	session,
}: {
	session: SessionData;
}) {
	const [page, setPage] = useState(0);
	const [agentOnly, setAgentOnly] = useState(false);
	const [openFilterMenu, setOpenFilterMenu] = useState<string | null>(null);
	const [expandedEntryId, setExpandedEntryId] = useState<string | null>(null);
	const [selectedEvents, setSelectedEvents] = useState<Set<string>>(
		() => new Set(),
	);
	const [selectedTools, setSelectedTools] = useState<Set<string>>(
		() => new Set(),
	);
	const [selectedDecisions, setSelectedDecisions] = useState<Set<Decision>>(
		() => new Set(),
	);
	const [detailToggles, setDetailToggles] = useState<Set<DetailToggle>>(
		() => new Set(),
	);

	const entries = useMemo(() => {
		const items: TimelineEntry[] = [];
		const eventContexts = [...session.events].sort((a, b) =>
			a.timestamp.localeCompare(b.timestamp),
		);
		const claimedEventIndexes = new Set<number>();

		for (const [resultIndex, r] of session.results.entries()) {
			const d = resolveDecision(r.findings);
			const matched = findMatchingEvent(session.events, claimedEventIndexes, r);
			const outputCommand = commandFromOutput(r.output);
			const outputText = outputSummary(r.output);
			const outputDetails = toolInputDetails(r.output);
			if (matched) {
				claimedEventIndexes.add(matched.index);
				const drilldown = mergeDrilldown(
					mergeDrilldown(eventDrilldown(r), outputDetails),
					eventDrilldown(matched.event),
				);
				items.push({
					id: `${session.id}:hook:${matched.index}:${resultIndex}:${matched.event.event_name}:${matched.event.timestamp}:${r.timestamp}:${matched.event.tool_name}`,
					time:
						r.timestamp > matched.event.timestamp
							? r.timestamp
							: matched.event.timestamp,
					type: "hook",
					label: matched.event.event_name,
					detail: eventDetail(matched.event),
					sessionId: session.id,
					platform: matched.event.platform,
					eventName: matched.event.event_name,
					toolName: matched.event.tool_name,
					eventTime: matched.event.timestamp,
					resultTime: r.timestamp,
					decision: d,
					resultLabel: `Result: ${d}`,
					resultDetail: resultDetail(r),
					findingCount: r.findings.length,
					errorCount: r.errors?.length ?? 0,
					findings: timelineFindings(session.id, resultIndex, r.findings),
					flagItemType: "result",
					flagItemId: `${session.id}:result:${r.timestamp}`,
					flagLabel: `${matched.event.event_name} result ${d} in session ${session.id.slice(0, 12)}`,
					...drilldown,
					command: drilldown.command ?? r.command ?? outputCommand,
					tool_output: drilldown.tool_output ?? r.tool_output ?? outputText,
				});
				continue;
			}

			const fallback = findNearbyDrilldown(
				eventContexts,
				r.timestamp,
				r.event_name,
				r.tool_name,
			);
			const drilldown = mergeDrilldown(
				mergeDrilldown(eventDrilldown(r), outputDetails),
				fallback,
			);
			items.push({
				id: `${session.id}:result:${resultIndex}:${r.event_name}:${r.timestamp}:${r.tool_name}`,
				time: r.timestamp,
				type: "result",
				label: `Result: ${d}`,
				detail: resultDetail(r),
				sessionId: session.id,
				platform: r.platform,
				eventName: r.event_name,
				toolName: r.tool_name,
				resultTime: r.timestamp,
				decision: d,
				findingCount: r.findings.length,
				errorCount: r.errors?.length ?? 0,
				findings: timelineFindings(session.id, resultIndex, r.findings),
				flagItemType: "result",
				flagItemId: `${session.id}:result:${r.timestamp}`,
				flagLabel: `Result ${d} in session ${session.id.slice(0, 12)}`,
				...drilldown,
				command: drilldown.command ?? r.command ?? outputCommand,
				tool_output: drilldown.tool_output ?? r.tool_output ?? outputText,
			});
		}

		for (const [index, e] of session.events.entries()) {
			if (claimedEventIndexes.has(index)) continue;
			const drilldown = eventDrilldown(e);
			items.push({
				id: `${session.id}:event:${index}:${e.event_name}:${e.timestamp}:${e.tool_name}`,
				time: e.timestamp,
				type: "event",
				label: e.event_name,
				detail: eventDetail(e),
				sessionId: session.id,
				platform: e.platform,
				eventName: e.event_name,
				toolName: e.tool_name,
				eventTime: e.timestamp,
				flagItemType: "event",
				flagItemId: `${session.id}:${e.event_name}:${e.timestamp}`,
				flagLabel: `${e.event_name} in session ${session.id.slice(0, 12)}`,
				...drilldown,
			});
		}

		for (const [findingIndex, f] of session.findings.entries()) {
			if (isDuplicateFindingEntry(f, session.results)) continue;
			const msg = f.message ?? "";
			const dec = f.decision ?? "context";
			const fallback = findNearbyDrilldown(
				eventContexts,
				f.timestamp,
				f.event_name,
				f.tool_name,
			);
			const drilldown = mergeDrilldown(eventDrilldown(f), fallback);
			items.push({
				id: `${session.id}:finding:${findingIndex}:${f.rule_id}:${f.timestamp}:${f.tool_name}`,
				time: f.timestamp,
				type: "finding",
				label: f.rule_id,
				detail: `${f.severity} → ${dec}: ${msg.slice(0, 80) || "(no message)"}`,
				sessionId: session.id,
				platform: f.platform,
				eventName: f.event_name,
				toolName: f.tool_name,
				eventTime: f.timestamp,
				decision: dec,
				findingCount: 1,
				flagItemType: "finding",
				flagItemId: `${session.id}:${f.rule_id}:${f.timestamp}`,
				flagLabel: `${f.rule_id} (${f.severity} ${dec}) in session ${session.id.slice(0, 12)}`,
				...drilldown,
			});
		}

		for (const [subprocessIndex, s] of session.subprocesses.entries()) {
			items.push({
				id: `${session.id}:subprocess:${subprocessIndex}:${s.timestamp}:${s.command}`,
				time: s.timestamp,
				type: "subprocess",
				label: s.command.slice(0, 40),
				detail: `exit ${s.returncode} (${s.duration_ms}ms)`,
				sessionId: session.id,
				eventName: s.event_name,
				eventTime: s.timestamp,
				decision: s.returncode === 0 ? "allow" : "deny",
				flagItemType: "event",
				flagItemId: `${session.id}:subprocess:${s.timestamp}`,
				flagLabel: `${s.command.slice(0, 30)} (exit ${s.returncode}) in session ${session.id.slice(0, 12)}`,
				command: s.command,
				tool_output:
					(s.stdout ? `stdout:\n${s.stdout}` : "") +
					(s.stderr ? `\nstderr:\n${s.stderr}` : ""),
			});
		}

		return items.sort((a, b) => b.time.localeCompare(a.time));
	}, [session]);

	const filteredEntries = useMemo(() => {
		const nestedMatches = entries.filter((entry) =>
			matchesNestedFilters(
				entry,
				selectedEvents,
				selectedTools,
				selectedDecisions,
				detailToggles,
			),
		);
		if (!agentOnly) return nestedMatches;
		return nestedMatches.filter((e) => {
			if (e.type === "event" || e.type === "hook") {
				return (
					e.label === "PreToolUse" ||
					e.label === "PostToolUse" ||
					e.label === "PermissionRequest" ||
					e.label === "PostToolUseFailure"
				);
			}
			if (e.type === "finding") {
				return true;
			}
			if (e.type === "result") {
				return !e.detail.startsWith("0 findings, 0 errors");
			}
			if (e.type === "subprocess") {
				return true;
			}
			return true;
		});
	}, [
		entries,
		selectedEvents,
		selectedTools,
		selectedDecisions,
		detailToggles,
		agentOnly,
	]);

	const eventOptions = useMemo(
		() =>
			[...new Set(entries.flatMap((entry) => entry.eventName ?? []))].sort(),
		[entries],
	);
	const toolOptions = useMemo(
		() => [...new Set(entries.flatMap((entry) => entry.toolName ?? []))].sort(),
		[entries],
	);
	const decisionOptions = useMemo(
		() => [...new Set(entries.flatMap((entry) => entry.decision ?? []))].sort(),
		[entries],
	);

	const resetNestedPaging = () => {
		setPage(0);
		setExpandedEntryId(null);
	};

	const pageCount = Math.max(1, Math.ceil(filteredEntries.length / PAGE_SIZE));
	const pageEntries = filteredEntries.slice(
		page * PAGE_SIZE,
		(page + 1) * PAGE_SIZE,
	);

	return (
		<div className="flex h-[520px] min-w-0 w-full flex-col overflow-hidden border-t border-border bg-background/50">
			<div className="flex flex-col gap-2 px-4 py-2 border-b border-border bg-background/30 text-xs">
				<div className="flex flex-wrap items-center justify-between gap-2">
					<span className="text-muted-foreground font-medium">
						Timeline Log
					</span>
					<label className="flex items-center gap-1.5 cursor-pointer text-[10px] text-muted-foreground hover:text-foreground select-none">
						<input
							type="checkbox"
							checked={agentOnly}
							onChange={(e) => {
								setAgentOnly(e.target.checked);
								resetNestedPaging();
							}}
							className="rounded border-border text-primary focus:ring-primary h-3 w-3"
						/>
						Focus on Agent Behavior (Hide Noise)
					</label>
				</div>
				<div className="flex flex-wrap gap-x-4 gap-y-1.5 text-[10px]">
					<NestedFilterGroup label="Event">
						<NestedMultiSelectMenu
							menuId="event"
							openMenuId={openFilterMenu}
							setOpenMenuId={setOpenFilterMenu}
							options={eventOptions}
							selected={selectedEvents}
							onToggle={(eventName) => {
								setSelectedEvents((current) =>
									toggleSetValue(current, eventName),
								);
								resetNestedPaging();
							}}
						/>
					</NestedFilterGroup>
					<NestedFilterGroup label="Tool">
						<NestedMultiSelectMenu
							menuId="tool"
							openMenuId={openFilterMenu}
							setOpenMenuId={setOpenFilterMenu}
							options={toolOptions}
							selected={selectedTools}
							onToggle={(toolName) => {
								setSelectedTools((current) =>
									toggleSetValue(current, toolName),
								);
								resetNestedPaging();
							}}
						/>
					</NestedFilterGroup>
					<NestedFilterGroup label="Decision">
						<NestedMultiSelectMenu
							menuId="decision"
							openMenuId={openFilterMenu}
							setOpenMenuId={setOpenFilterMenu}
							options={decisionOptions}
							selected={selectedDecisions}
							onToggle={(decision) => {
								setSelectedDecisions((current) =>
									toggleSetValue(current, decision),
								);
								resetNestedPaging();
							}}
						/>
					</NestedFilterGroup>
					<NestedFilterGroup label="Details">
						{DETAIL_TOGGLES.map((toggle) => (
							<NestedFilterChip
								key={toggle}
								active={detailToggles.has(toggle)}
								onClick={() => {
									setDetailToggles((current) =>
										toggleSetValue(current, toggle),
									);
									resetNestedPaging();
								}}
							>
								{DETAIL_TOGGLE_LABELS[toggle]}
							</NestedFilterChip>
						))}
					</NestedFilterGroup>
				</div>
			</div>
			<div className="relative min-h-0 flex-1 overflow-y-auto p-4 pl-10">
				<div className="absolute left-[21px] top-6 bottom-6 w-px bg-border" />
				{pageEntries.map((entry) => {
					const isExpanded = expandedEntryId === entry.id;
					const diffText = focusedEditDiff(entry);
					const missingToolBodyReason = hasToolCallBody(entry, diffText)
						? null
						: missingToolCallBodyReason(entry);
					return (
						<div
							key={entry.id}
							className="relative flex flex-col mb-3 last:mb-0 group border-b border-border/10 pb-2"
						>
							<button
								type="button"
								aria-label={`${entry.type} ${entry.label} ${entry.resultLabel ?? ""}`.trim()}
								aria-expanded={isExpanded}
								className={cn(
									"relative flex w-full cursor-pointer items-start gap-3 rounded p-1.5 pr-9 text-left transition-colors hover:bg-muted/10 focus:outline-none focus:ring-1 focus:ring-primary/50",
									isExpanded && "bg-primary/10 ring-1 ring-primary/30",
								)}
								onClick={() =>
									setExpandedEntryId((current) =>
										current === entry.id ? null : entry.id,
									)
								}
							>
								<div
									className={cn(
										"absolute left-0 top-3 w-[7px] h-[7px] rounded-full border border-border z-10",
										entry.decision
											? DECISION_DOT_STYLE[entry.decision]
											: "bg-muted-foreground",
									)}
								/>
								<div className="ml-4 min-w-0 flex-1">
									<div className="flex items-center gap-2">
										<span
											className={cn(
												"text-[10px] uppercase px-1 py-0.5 rounded",
												entryTypeClass(entry.type),
											)}
										>
											{entry.type}
										</span>
										<span className="text-xs font-medium truncate">
											{entry.label}
										</span>
										{entry.resultLabel && (
											<>
												<span className="text-muted-foreground">→</span>
												<span className="text-xs font-medium truncate">
													{entry.resultLabel}
												</span>
											</>
										)}
										<div className="ml-auto flex shrink-0 items-center gap-1.5">
											<span className="text-[10px] text-muted-foreground">
												{new Date(entry.time).toLocaleTimeString()}
											</span>
										</div>
									</div>
									<div className="text-[10px] text-muted-foreground mt-0.5 truncate">
										{entry.resultDetail
											? `${entry.detail} · ${entry.resultDetail}`
											: entry.detail}
									</div>
								</div>
							</button>
							<div className="absolute right-2 top-2 z-20">
								<FlagButton
									itemType={entry.flagItemType}
									itemId={entry.flagItemId}
									label={entry.flagLabel}
									compact
								/>
							</div>
							{isExpanded && (
								<div className="ml-10 mt-2 p-3 bg-muted/20 border border-border/30 rounded text-[10px] space-y-2 font-mono">
									<div className="grid grid-cols-2 gap-x-4 gap-y-1 rounded border border-border/20 bg-background/30 p-2">
										{auditRows(entry).map(([label, value]) => (
											<div key={label} className="min-w-0">
												<span className="text-muted-foreground select-none">
													{label}:{" "}
												</span>
												<span className="text-foreground break-all">
													{value}
												</span>
											</div>
										))}
									</div>
									{entry.candidate_paths &&
										entry.candidate_paths.length > 0 && (
											<div>
												<span className="text-muted-foreground select-none">
													File(s):{" "}
												</span>
												<span className="text-foreground break-all">
													{entry.candidate_paths.join(", ")}
												</span>
											</div>
										)}
									{entry.tool_context && entry.tool_context.length > 0 && (
										<div>
											<span className="text-muted-foreground select-none">
												{toolContextLabel(entry)}:{" "}
											</span>
											<span className="text-foreground break-all">
												{entry.tool_context.join(", ")}
											</span>
										</div>
									)}
									{entry.url_context && entry.url_context.length > 0 && (
										<div>
											<span className="text-muted-foreground select-none">
												URL(s):{" "}
											</span>
											<span className="text-foreground break-all">
												{entry.url_context.join(", ")}
											</span>
										</div>
									)}
									{entry.findings && entry.findings.length > 0 && (
										<div>
											<span className="text-muted-foreground select-none">
												Grouped finding(s):{" "}
											</span>
											<div className="mt-1 space-y-1">
												{entry.findings.map((finding) => (
													<div
														key={finding.id}
														className="rounded border border-signal-ask/20 bg-signal-ask/5 p-2"
													>
														<div className="flex flex-wrap items-center gap-2">
															<span className="rounded bg-signal-ask/10 px-1 py-0.5 uppercase text-signal-ask">
																Finding
															</span>
															<span className="font-medium text-foreground">
																{finding.ruleId}
															</span>
														</div>
														<div className="mt-1 text-muted-foreground">
															{findingSummary(finding)}
														</div>
														{finding.additionalContext && (
															<div className="mt-1 break-all text-foreground">
																{finding.additionalContext}
															</div>
														)}
													</div>
												))}
											</div>
										</div>
									)}
									{(entry.model || entry.provider) && (
										<div>
											<span className="text-muted-foreground select-none">
												AI Model:{" "}
											</span>
											<span className="text-foreground">
												{entry.model || "Unknown"} (
												{entry.provider || "Unknown"})
											</span>
										</div>
									)}
									{entry.command && (
										<div>
											<span className="text-muted-foreground select-none">
												Command:{" "}
											</span>
											<pre className="mt-1 p-2 bg-background/50 border border-border/20 rounded max-w-full overflow-x-auto text-foreground whitespace-pre-wrap">
												{entry.command}
											</pre>
										</div>
									)}
									{diffText && (
										<div>
											<span className="text-muted-foreground select-none">
												Patch / focused diff:{" "}
											</span>
											<pre className="mt-1 max-h-56 max-w-full overflow-auto rounded border border-border/20 bg-background/50 p-2 text-foreground whitespace-pre-wrap">
												{diffText}
											</pre>
										</div>
									)}
									{(entry.edit_before || entry.edit_after) && (
										<div>
											<span className="text-muted-foreground select-none">
												Focused edit:{" "}
											</span>
											<div className="mt-1 grid gap-2 md:grid-cols-2">
												{entry.edit_before && (
													<div className="min-w-0">
														<div className="mb-1 text-muted-foreground">
															Before
														</div>
														<pre className="max-h-48 max-w-full overflow-auto rounded border border-border/20 bg-background/50 p-2 text-foreground whitespace-pre-wrap">
															{entry.edit_before}
														</pre>
													</div>
												)}
												{entry.edit_after && (
													<div className="min-w-0">
														<div className="mb-1 text-muted-foreground">
															After
														</div>
														<pre className="max-h-48 max-w-full overflow-auto rounded border border-border/20 bg-background/50 p-2 text-foreground whitespace-pre-wrap">
															{entry.edit_after}
														</pre>
													</div>
												)}
											</div>
										</div>
									)}
									{entry.tool_input_json && (
										<div>
											<span className="text-muted-foreground select-none">
												Tool input:{" "}
											</span>
											<pre className="mt-1 max-h-56 max-w-full overflow-auto rounded border border-border/20 bg-background/50 p-2 text-foreground whitespace-pre-wrap">
												{entry.tool_input_json}
											</pre>
										</div>
									)}
									{entry.tool_output && (
										<div>
											<span className="text-muted-foreground select-none">
												Output:{" "}
											</span>
											<div className="mt-1 space-y-1.5">
												{formattedHookOutputSections(entry.tool_output).map(
													(section) => (
														<div
															key={`${section.label}:${section.value.slice(0, 32)}`}
															className={cn(
																"rounded border p-2",
																outputSectionClass(section.variant),
															)}
														>
															<div className="mb-1 text-[9px] uppercase tracking-wider text-muted-foreground">
																{section.label}
															</div>
															<pre className="max-h-56 max-w-full overflow-auto whitespace-pre-wrap text-foreground">
																{section.value}
															</pre>
														</div>
													),
												)}
											</div>
										</div>
									)}
									{missingToolBodyReason && (
										<div className="rounded border border-signal-warn/20 bg-signal-warn/5 p-2 text-signal-warn">
											<div className="mb-1 text-[9px] uppercase tracking-wider text-muted-foreground">
												Tool input unavailable
											</div>
											<div className="text-foreground">
												{missingToolBodyReason}
											</div>
										</div>
									)}
									{!hasDrilldown(entry) && entry.type !== "hook" && (
										<div className="text-muted-foreground italic">
											No correlated drill-down data available for this entry.
										</div>
									)}
								</div>
							)}
						</div>
					);
				})}
				{pageEntries.length === 0 && (
					<div className="rounded border border-border/30 bg-muted/10 px-3 py-4 text-center text-[10px] text-muted-foreground">
						No timeline entries match the current filters.
					</div>
				)}
			</div>
			{pageCount > 1 && (
				<div className="flex items-center justify-between px-4 py-2 border-t border-border text-[10px] text-muted-foreground sticky bottom-0 bg-background/95 backdrop-blur-sm">
					<span>{filteredEntries.length} entries total</span>
					<div className="flex gap-2">
						<button
							type="button"
							disabled={page === 0}
							onClick={() => setPage((p) => p - 1)}
							className="hover:text-foreground disabled:opacity-30"
						>
							← Prev
						</button>
						<span>
							{page + 1} / {pageCount}
						</span>
						<button
							type="button"
							disabled={page + 1 >= pageCount}
							onClick={() => setPage((p) => p + 1)}
							className="hover:text-foreground disabled:opacity-30"
						>
							Next →
						</button>
					</div>
				</div>
			)}
		</div>
	);
});

function NestedFilterGroup({
	label,
	children,
}: {
	label: string;
	children: ReactNode;
}) {
	return (
		<div className="flex flex-wrap items-center gap-1.5">
			<span className="text-muted-foreground">{label}:</span>
			{children}
		</div>
	);
}

function NestedFilterChip({
	active,
	onClick,
	children,
}: {
	active: boolean;
	onClick: () => void;
	children: ReactNode;
}) {
	return (
		<button
			type="button"
			onClick={onClick}
			className={cn(
				"rounded border px-1.5 py-0.5 transition-colors",
				active
					? "border-primary/40 bg-primary/15 text-primary"
					: "border-border/40 bg-muted/20 text-muted-foreground hover:text-foreground",
			)}
		>
			{children}
		</button>
	);
}

function NestedMultiSelectMenu<T extends string>({
	menuId,
	openMenuId,
	setOpenMenuId,
	options,
	selected,
	onToggle,
}: {
	menuId: string;
	openMenuId: string | null;
	setOpenMenuId: (menuId: string | null) => void;
	options: T[];
	selected: Set<T>;
	onToggle: (option: T) => void;
}) {
	const isOpen = openMenuId === menuId;
	const selectionLabel =
		selected.size === 0 ? "All" : `${selected.size} selected`;

	return (
		<div className="relative">
			<button
				type="button"
				onClick={() => setOpenMenuId(isOpen ? null : menuId)}
				className={cn(
					"rounded border px-1.5 py-0.5 transition-colors",
					selected.size > 0 || isOpen
						? "border-primary/40 bg-primary/15 text-primary"
						: "border-border/40 bg-muted/20 text-muted-foreground hover:text-foreground",
				)}
			>
				{selectionLabel}
			</button>
			{isOpen && (
				<div className="absolute left-0 top-full z-30 mt-1 min-w-44 rounded border border-border bg-popover p-2 shadow-lg">
					<div className="mb-1 text-[9px] uppercase tracking-wider text-muted-foreground">
						Options
					</div>
					<div className="max-h-48 space-y-1 overflow-y-auto">
						{options.map((option) => (
							<label
								key={option}
								className="flex cursor-pointer items-center gap-2 rounded px-1 py-0.5 text-muted-foreground hover:bg-muted/20 hover:text-foreground"
							>
								<input
									type="checkbox"
									checked={selected.has(option)}
									onChange={() => onToggle(option)}
									className="h-3 w-3 rounded border-border text-primary focus:ring-primary"
								/>
								<span>{option}</span>
							</label>
						))}
					</div>
				</div>
			)}
		</div>
	);
}
