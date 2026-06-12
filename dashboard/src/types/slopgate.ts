export type Platform = "claude" | "codex" | "opencode" | "cursor" | "unknown";
export type PlatformSource = "explicit" | "defaulted" | "normalized" | "unknown";
export type LineageRole = "parent" | "child" | "mirror" | "child_mirror" | "raw";
export type LineageConfidence = "explicit" | "inferred" | "none";

export const EVENT_NAMES = [
	"AfterAgentResponse",
	"AfterAgentThought",
	"CommandExecuted",
	"ConfigChange",
	"CwdChanged",
	"Elicitation",
	"ElicitationResult",
	"FileChanged",
	"InstructionsLoaded",
	"Notification",
	"PermissionDenied",
	"PermissionReplied",
	"PermissionRequest",
	"PostCompact",
	"PostToolBatch",
	"PostToolUse",
	"PostToolUseFailure",
	"PreCompact",
	"PreToolUse",
	"SessionEnd",
	"SessionError",
	"SessionStart",
	"SessionStatus",
	"Setup",
	"ShellEnv",
	"Stop",
	"StopFailure",
	"SubagentStart",
	"SubagentStop",
	"TaskCompleted",
	"TaskCreated",
	"TeammateIdle",
	"UserPromptExpansion",
	"UserPromptSubmit",
	"WorkspaceOpen",
	"WorktreeCreate",
	"WorktreeRemove",
] as const;

export type EventName = (typeof EVENT_NAMES)[number];

export type Decision =
	| "allow"
	| "deny"
	| "block"
	| "ask"
	| "context"
	| "warn"
	| "info";

export type Severity = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export type PlatformCapability = "full" | "partial" | "degraded";
export type EnforcementMode = "outside_repo" | "repo_strict" | "repo_relaxed";

export interface TraceMetadata {
	platform_capability?: PlatformCapability | string | null;
	degraded_reason?: string | null;
	enforcement_mode?: EnforcementMode | string | null;
	resolved_repo_root?: string | null;
	parent_session_id?: string | null;
	root_session_id?: string | null;
	origin_platform?: Platform | null;
	origin_session_id?: string | null;
	platform_source?: PlatformSource | null;
	subagent_type?: string | null;
	spawn_description?: string | null;
	lineage_role?: LineageRole | null;
}

export interface HookEvent extends TraceMetadata {
	timestamp: string;
	platform: Platform;
	event_name: EventName;
	session_id: string;
	tool_name: string;
	candidate_paths: string[];
	languages: string[];
	model?: string | null;
	provider?: string | null;
	command?: string | null;
	tool_output?: string | null;
	tool_input?: Record<string, unknown> | null;
}

export interface RuleFinding extends TraceMetadata {
	timestamp: string;
	platform: Platform;
	event_name: EventName;
	session_id: string;
	tool_name: string;
	rule_id: string;
	severity: Severity;
	decision: Decision | null;
	message: string | null;
	additional_context: string | null;
	metadata: Record<string, unknown>;
	model?: string | null;
	provider?: string | null;
	command?: string | null;
	tool_output?: string | null;
	tool_input?: Record<string, unknown> | null;
}

export interface HookResult extends TraceMetadata {
	timestamp: string;
	platform: Platform;
	event_name: EventName;
	session_id: string;
	tool_name: string;
	findings: Array<{
		rule_id: string;
		severity: Severity;
		decision: Decision | null;
		message: string | null;
		additional_context?: string | null;
		metadata?: Record<string, unknown>;
	}>;
	errors: string[] | null;
	output: Record<string, unknown> | null;
	skipped?: boolean;
	reason?: string;
	model?: string | null;
	provider?: string | null;
	command?: string | null;
	tool_output?: string | null;
	tool_input?: Record<string, unknown> | null;
}

export interface SubprocessRun {
	timestamp: string;
	event_name: string;
	session_id: string;
	command: string;
	cwd: string;
	returncode: number;
	stdout: string;
	stderr: string;
	duration_ms: number;
}

export interface RuntimeConfig {
	disabled_rules: Array<{ rule_id: string; disabled_date: string }>;
	severity_overrides: Array<{
		rule_id: string;
		original: Severity;
		override: Severity;
	}>;
	skip_paths: string[];
	skip_repos: string[];
}

export interface OperationalCountRow {
	label: string;
	count: number;
}

export interface OperationalContext {
	platformCapabilities: OperationalCountRow[];
	enforcementModes: OperationalCountRow[];
	degradedReasons: OperationalCountRow[];
	repoRoots: OperationalCountRow[];
	pathlessResults: number;
	repeatedDenials: OperationalCountRow[];
	resolutionRate: number | null;
	blockedSessions: number;
	resolvedBlockedSessions: number;
}

export type HarnessStatusValue =
	| "installed"
	| "partial"
	| "missing"
	| "disabled"
	| "error";
export type HarnessCapability = "full" | "partial" | "degraded";

export interface HarnessDryRunStatus {
	available: boolean;
	ok: boolean;
	returncode?: number;
	note?: string;
}

export interface HarnessPlatformStatus {
	id: "claude" | "codex" | "opencode";
	label: string;
	capability: HarnessCapability;
	support: string;
	status: HarnessStatusValue;
	config_path: string;
	config_exists: boolean;
	expected_events: string[];
	configured_events: string[];
	missing_events: string[];
	hook_entry_count: number;
	slopgate_command_count: number;
	all_commands_reference_slopgate: boolean;
	dry_run: HarnessDryRunStatus;
	error?: string | null;
	feature_flag_path?: string;
	feature_flag_enabled?: boolean;
	plugin_contains_slopgate?: boolean;
	disabled_plugin_present?: boolean;
}

export interface HarnessStatusResponse {
	ok: boolean;
	checked_at?: string;
	ssh_host?: string;
	platforms?: HarnessPlatformStatus[];
	error?: string;
}

export type TimeWindow = "1h" | "6h" | "24h" | "7d" | "30d";

export interface FilterState {
	timeWindow: TimeWindow;
	platforms: Platform[];
	pathFilter: string | null;
}

// ── Rule configuration types ───────────────────────────────────────────────

export type RuleAction = "deny" | "block" | "warn" | "ask" | "context";
export type RuleTarget = "content" | "path" | "command";

/** A regex/declarative rule entry from defaults.json or user config */
export interface RegexRuleConfig {
	rule_id: string;
	title: string;
	severity: Severity;
	events: string[];
	target: RuleTarget;
	path_globs?: string[];
	exclude_path_globs?: string[];
	patterns?: string[];
	action: RuleAction;
	message?: string;
	additional_context?: string;
	tool_matchers?: string[];
	case_sensitive?: boolean;
	multiline?: boolean;
}

/** Merged config injected by build-standalone as window.__SLOPGATE_CONFIG__ */
export interface SlopgateConfig {
	/** rule_id → enabled (bool). Missing key means default (true). */
	enabled_rules: Record<string, boolean>;
	/** All regex rules with per-rule exclude_path_globs merged from user config */
	regex_rules: RegexRuleConfig[];
	skip_paths: string[];
}

/** Rich rule metadata used by RuleManager UI */
export interface RuleMetadata {
	rule_id: string;
	title: string;
	description: string;
	severity: Severity;
	/** Derived from rule_id prefix, e.g. PY-CODE → python, GIT → git */
	category: string;
	source: "builtin" | "regex";
	enabled: boolean;
	fireCount: number;
	action: RuleAction;
	path_globs: string[];
	exclude_path_globs: string[];
	events: string[];
}

// Investigation flag system
export type FlagTarget = "openclaw" | "claude" | "codex";
export type FlagMode = "on-direction" | "cron" | "heartbeat";
export type FlagItemType =
	| "event"
	| "finding"
	| "result"
	| "path"
	| "rule"
	| "session";

export interface InvestigationFlag {
	id: string;
	createdAt: string;
	itemType: FlagItemType;
	itemId: string; // session_id, rule_id, path, etc.
	label: string; // human-readable summary
	target: FlagTarget;
	mode: FlagMode;
	notes: string;
	resolved: boolean;
}
