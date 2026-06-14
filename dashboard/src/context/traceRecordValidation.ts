import type {
	Decision,
	EventName,
	HookEvent,
	HookResult,
	LineageRole,
	Platform,
	PlatformSource,
	RuleFinding,
	Severity,
	SubprocessRun,
} from "@/types/slopgate";
import { EVENT_NAMES } from "@/types/slopgate";

export type TraceRecordType =
	| "event"
	| "rule"
	| "result"
	| "subprocess"
	| "ignored";

export type AcceptedTraceRecord =
	| { type: "event"; record: HookEvent }
	| { type: "rule"; record: RuleFinding }
	| { type: "result"; record: HookResult }
	| { type: "subprocess"; record: SubprocessRun }
	| { type: "ignored" };

type TraceIdentity = {
	timestamp: string;
	event_name: string;
	session_id: string;
};

function hasTraceIdentity(
	obj: Record<string, unknown>,
): obj is Record<string, unknown> & TraceIdentity {
	return (
		typeof obj.timestamp === "string" &&
		typeof obj.event_name === "string" &&
		typeof obj.session_id === "string"
	);
}

export function classifyLine(
	obj: Record<string, unknown>,
): TraceRecordType | null {
	// subprocess: has command + returncode
	if ("command" in obj && "returncode" in obj) return "subprocess";
	// result rows intentionally do not carry event-only candidate path/language metadata.
	if ("findings" in obj && Array.isArray(obj.findings)) return "result";
	// rules.jsonl also contains timing/metric rows keyed by rule_id; those are not UI findings.
	if ("rule_id" in obj) {
		if (hasTraceIdentity(obj) && "decision" in obj && "severity" in obj)
			return "rule";
		return "ignored";
	}
	// event: has the full event identity shape, including candidate path/language metadata.
	if (hasTraceIdentity(obj)) return "event";
	return null;
}

function isStringArray(value: unknown): value is string[] {
	return (
		Array.isArray(value) && value.every((item) => typeof item === "string")
	);
}

function optionalString(value: unknown): string | null | undefined {
	if (typeof value === "string") return value;
	if (value === null) return null;
	if (value === undefined) return undefined;
	return null;
}

function objectRecord(value: unknown): Record<string, unknown> | null {
	if (typeof value !== "object" || value === null || Array.isArray(value)) {
		return null;
	}
	return Object.fromEntries(
		Object.entries(value).filter(([key]) => typeof key === "string"),
	);
}

function normalizeStringArray(value: unknown): string[] {
	return isStringArray(value) ? value : [];
}

function optionalAliasedStringArray(
	obj: Record<string, unknown>,
	keys: string[],
): string[] | undefined {
	const value = aliasedValue(obj, keys);
	if (typeof value === "string" && value.trim()) return [value.trim()];
	if (isStringArray(value)) return value.filter((item) => item.trim());
	return undefined;
}

function normalizePlatform(value: unknown): Platform {
	switch (value) {
		case "claude":
			return "claude";
		case "codex":
			return "codex";
		case "opencode":
			return "opencode";
		case "cursor":
			return "cursor";
		case "unknown":
			return "unknown";
		default:
			return "unknown";
	}
}

function normalizePlatformSource(
	value: unknown,
	rawPlatform: unknown,
): PlatformSource {
	switch (value) {
		case "explicit":
		case "defaulted":
		case "normalized":
		case "unknown":
			return value;
		default:
			if (rawPlatform === undefined || rawPlatform === null || rawPlatform === "") {
				return "unknown";
			}
			return normalizePlatform(rawPlatform) === "unknown"
				? "normalized"
				: "explicit";
	}
}

function normalizeLineageRole(value: unknown): LineageRole | null | undefined {
	if (value === undefined) return undefined;
	if (value === null) return null;
	switch (value) {
		case "parent":
		case "child":
		case "mirror":
		case "child_mirror":
		case "raw":
			return value;
		default:
			return null;
	}
}

function isEventName(value: unknown): value is EventName {
	return (
		typeof value === "string" &&
		EVENT_NAMES.some((eventName) => eventName === value)
	);
}

function normalizeEventName(value: unknown): EventName | null {
	return isEventName(value) ? value : null;
}

function normalizeSeverity(value: unknown): Severity {
	switch (value) {
		case "LOW":
			return "LOW";
		case "MEDIUM":
			return "MEDIUM";
		case "HIGH":
			return "HIGH";
		case "CRITICAL":
			return "CRITICAL";
		default:
			return "LOW";
	}
}

function normalizeDecision(value: unknown): Decision | null {
	switch (value) {
		case "allow":
			return "allow";
		case "deny":
			return "deny";
		case "block":
			return "block";
		case "ask":
			return "ask";
		case "context":
			return "context";
		case "warn":
			return "warn";
		case "info":
			return "info";
		default:
			return null;
	}
}

function traceMetadata(
	obj: Record<string, unknown>,
	includeBareTitle = false,
) {
	const originPlatform = optionalAliasedPlatform(obj, [
		"origin_platform",
		"originPlatform",
	]);
	const lineageRole = normalizeLineageRole(
		aliasedValue(obj, ["lineage_role", "lineageRole"]),
	);
	return {
		platform_capability: optionalString(obj.platform_capability),
		degraded_reason: optionalString(obj.degraded_reason),
		enforcement_mode: optionalString(obj.enforcement_mode),
		resolved_repo_root: optionalString(obj.resolved_repo_root),
		session_title: optionalAliasedString(obj, [
			"session_title",
			"sessionTitle",
			"thread_title",
			"threadTitle",
			"conversation_title",
			"conversationTitle",
			...(includeBareTitle ? ["title"] : []),
		]),
		session_title_source: optionalAliasedString(obj, [
			"session_title_source",
			"sessionTitleSource",
		]),
		session_identity_source: optionalAliasedString(obj, [
			"session_identity_source",
			"sessionIdentitySource",
		]),
		opencode_session_id: optionalAliasedString(obj, [
			"opencode_session_id",
			"opencodeSessionId",
			"opencodeSessionID",
		]),
		codex_session_id: optionalAliasedString(obj, [
			"codex_session_id",
			"codexSessionId",
			"codexSessionID",
			"thread_id",
			"threadId",
			"threadID",
			"conversation_id",
			"conversationId",
			"conversationID",
		]),
		secondary_session_ids: optionalAliasedStringArray(obj, [
			"secondary_session_ids",
			"secondarySessionIds",
		]),
		parent_session_id: optionalAliasedString(obj, [
			"parent_session_id",
			"parentSessionId",
			"parentSessionID",
		]),
		root_session_id: optionalAliasedString(obj, [
			"root_session_id",
			"rootSessionId",
			"rootSessionID",
		]),
		origin_platform: originPlatform,
		origin_session_id: optionalAliasedString(obj, [
			"origin_session_id",
			"originSessionId",
			"originSessionID",
		]),
		platform_source: normalizePlatformSource(
			aliasedValue(obj, ["platform_source", "platformSource"]),
			obj.platform,
		),
		subagent_type: optionalAliasedString(obj, ["subagent_type", "subagentType"]),
		spawn_description: optionalAliasedString(obj, [
			"spawn_description",
			"spawnDescription",
		]),
		lineage_role: lineageRole,
	};
}

function aliasedValue(
	obj: Record<string, unknown>,
	keys: string[],
): unknown | undefined {
	for (const key of keys) {
		if (key in obj) return obj[key];
	}
	return undefined;
}

function optionalAliasedString(
	obj: Record<string, unknown>,
	keys: string[],
): string | null | undefined {
	const value = aliasedValue(obj, keys);
	return optionalString(value);
}

function optionalAliasedPlatform(
	obj: Record<string, unknown>,
	keys: string[],
): Platform | null | undefined {
	const value = aliasedValue(obj, keys);
	if (value === undefined) return undefined;
	if (value === null) return null;
	return normalizePlatform(value);
}

function normalizeEventRecord(obj: Record<string, unknown>): HookEvent | null {
	if (!hasTraceIdentity(obj)) return null;
	const eventName = normalizeEventName(obj.event_name);
	if (!eventName) return null;
	return {
		timestamp: obj.timestamp,
		platform: normalizePlatform(obj.platform),
		event_name: eventName,
		session_id: obj.session_id,
		tool_name: typeof obj.tool_name === "string" ? obj.tool_name : "",
		candidate_paths: normalizeStringArray(obj.candidate_paths),
		languages: normalizeStringArray(obj.languages),
		model: optionalString(obj.model),
		provider: optionalString(obj.provider),
		command: optionalString(obj.command),
		tool_output: optionalString(obj.tool_output),
		tool_input:
			objectRecord(obj.tool_input) ??
			objectRecord(obj.toolInput) ??
			objectRecord(obj.tool_args) ??
			objectRecord(obj.input) ??
			objectRecord(obj.args) ??
			objectRecord(obj.arguments),
		...traceMetadata(obj, true),
	};
}

function normalizeRuleFindingRecord(
	obj: Record<string, unknown>,
): RuleFinding | null {
	if (!hasTraceIdentity(obj) || typeof obj.rule_id !== "string") return null;
	const eventName = normalizeEventName(obj.event_name);
	if (!eventName) return null;
	return {
		timestamp: obj.timestamp,
		platform: normalizePlatform(obj.platform),
		event_name: eventName,
		session_id: obj.session_id,
		tool_name: typeof obj.tool_name === "string" ? obj.tool_name : "",
		rule_id: obj.rule_id,
		severity: normalizeSeverity(obj.severity),
		decision: normalizeDecision(obj.decision),
		message: optionalString(obj.message) ?? null,
		additional_context: optionalString(obj.additional_context) ?? null,
		metadata: objectRecord(obj.metadata) ?? {},
		model: optionalString(obj.model),
		provider: optionalString(obj.provider),
		command: optionalString(obj.command),
		tool_output: optionalString(obj.tool_output),
		tool_input:
			objectRecord(obj.tool_input) ??
			objectRecord(obj.toolInput) ??
			objectRecord(obj.tool_args) ??
			objectRecord(obj.input) ??
			objectRecord(obj.args) ??
			objectRecord(obj.arguments),
		...traceMetadata(obj),
	};
}

function normalizeFindingSummary(
	value: unknown,
): HookResult["findings"][number] | null {
	const finding = objectRecord(value);
	if (!finding) return null;
	return {
		rule_id: typeof finding.rule_id === "string" ? finding.rule_id : "",
		severity: normalizeSeverity(finding.severity),
		decision: normalizeDecision(finding.decision),
		message: optionalString(finding.message) ?? null,
		additional_context: optionalString(finding.additional_context) ?? null,
		metadata: objectRecord(finding.metadata) ?? {},
	};
}

function normalizeResultRecord(
	obj: Record<string, unknown>,
): HookResult | null {
	if (!hasTraceIdentity(obj) || !Array.isArray(obj.findings)) return null;
	const eventName = normalizeEventName(obj.event_name);
	if (!eventName) return null;
	return {
		timestamp: obj.timestamp,
		platform: normalizePlatform(obj.platform),
		event_name: eventName,
		session_id: obj.session_id,
		tool_name: typeof obj.tool_name === "string" ? obj.tool_name : "",
		findings: obj.findings.flatMap((finding) => {
			const normalized = normalizeFindingSummary(finding);
			return normalized ? [normalized] : [];
		}),
		errors: normalizeStringArray(obj.errors),
		output: objectRecord(obj.output),
		skipped: typeof obj.skipped === "boolean" ? obj.skipped : false,
		reason: optionalString(obj.reason) ?? undefined,
		model: optionalString(obj.model),
		provider: optionalString(obj.provider),
		command: optionalString(obj.command),
		tool_output: optionalString(obj.tool_output),
		tool_input:
			objectRecord(obj.tool_input) ??
			objectRecord(obj.toolInput) ??
			objectRecord(obj.tool_args) ??
			objectRecord(obj.input) ??
			objectRecord(obj.args) ??
			objectRecord(obj.arguments),
		...traceMetadata(obj),
	};
}

function isHookEventRecord(obj: unknown): obj is HookEvent {
	if (typeof obj !== "object" || obj === null) return false;
	const o = obj as Record<string, unknown>;
	return (
		hasTraceIdentity(o) &&
		normalizeEventName(o.event_name) !== null &&
		normalizePlatform(o.platform) === o.platform &&
		typeof o.tool_name === "string" &&
		isStringArray(o.candidate_paths) &&
		isStringArray(o.languages)
	);
}

function isRuleFindingRecord(obj: unknown): obj is RuleFinding {
	if (typeof obj !== "object" || obj === null) return false;
	const o = obj as Record<string, unknown>;
	return (
		hasTraceIdentity(o) &&
		normalizeEventName(o.event_name) !== null &&
		normalizePlatform(o.platform) === o.platform &&
		typeof o.tool_name === "string" &&
		typeof o.rule_id === "string" &&
		normalizeSeverity(o.severity) === o.severity &&
		(o.decision === null || normalizeDecision(o.decision) === o.decision) &&
		(typeof o.message === "string" || o.message === null) &&
		(typeof o.additional_context === "string" ||
			o.additional_context === null) &&
		typeof o.metadata === "object" &&
		o.metadata !== null
	);
}

function isHookResultRecord(obj: unknown): obj is HookResult {
	if (typeof obj !== "object" || obj === null) return false;
	const o = obj as Record<string, unknown>;
	return (
		hasTraceIdentity(o) &&
		normalizeEventName(o.event_name) !== null &&
		normalizePlatform(o.platform) === o.platform &&
		typeof o.tool_name === "string" &&
		Array.isArray(o.findings) &&
		(Array.isArray(o.errors) || o.errors === null) &&
		(typeof o.output === "object" ||
			o.output === null ||
			o.output === undefined)
	);
}

function isSubprocessRunRecord(obj: unknown): obj is SubprocessRun {
	if (typeof obj !== "object" || obj === null) return false;
	const o = obj as Record<string, unknown>;
	// duration_ms may be absent in raw log records; match snapshot default (0).
	const out = o as Record<string, unknown> & { duration_ms?: number };
	out.duration_ms ??= 0;
	return (
		typeof o.timestamp === "string" &&
		typeof o.event_name === "string" &&
		typeof o.session_id === "string" &&
		typeof o.command === "string" &&
		typeof o.cwd === "string" &&
		typeof o.returncode === "number" &&
		typeof o.stdout === "string" &&
		typeof o.stderr === "string" &&
		typeof out.duration_ms === "number"
	);
}

export function coerceTraceRecord(
	obj: Record<string, unknown>,
): AcceptedTraceRecord | null {
	const type = classifyLine(obj);
	if (type === null) return { type: "ignored" };
	if (type === "event") {
		const record = isHookEventRecord(obj) ? obj : normalizeEventRecord(obj);
		if (record) return { type, record };
	}
	if (type === "rule") {
		const record = isRuleFindingRecord(obj)
			? obj
			: normalizeRuleFindingRecord(obj);
		if (record) return { type, record };
	}
	if (type === "result") {
		const record = isHookResultRecord(obj) ? obj : normalizeResultRecord(obj);
		if (record) return { type, record };
	}
	if (type === "subprocess" && isSubprocessRunRecord(obj))
		return { type, record: obj };
	if (type === "ignored") return { type };
	return null;
}
