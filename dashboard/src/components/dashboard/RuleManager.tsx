import {
	AlertTriangle,
	Check,
	ChevronDown,
	ChevronRight,
	Globe,
	Loader2,
	Plus,
	RotateCcw,
	Save,
	Search,
	Wifi,
	WifiOff,
	X,
} from "lucide-react";
import { memo, useCallback, useMemo, useState } from "react";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { useRulesConfig } from "@/context/useRulesConfig";
import { SEVERITY_COLORS } from "@/lib/chartTheme";
import { getRuleDescription } from "@/lib/ruleDescriptions";
import { cn } from "@/lib/utils";
import type { RuleMetadata, Severity, SlopgateConfig } from "@/types/slopgate";
import type { RuleHookSurface, RuleSurfaceAction } from "@/types/slopgate";

interface Props {
	/** Fire counts from trace data (rule_id → count) */
	fireCounts: Map<string, number>;
}

const TABLE_COLSPAN = 10;
const QUALITY_LINT_RULE_ID = "QUALITY-LINT-001";
const HOOK_ACTIONS = [
	"deny",
	"ask",
	"block",
	"allow",
	"context",
	"warn",
] as const satisfies readonly RuleSurfaceAction[];
const HOOK_EVENT_OPTIONS = [
	"PreToolUse",
	"PermissionRequest",
	"PostToolUse",
	"UserPromptSubmit",
	"Stop",
] as const;

const CLI_RULE_IDS = [
	"assertion-free-test",
	"assertion-roulette",
	"banned-any",
	"boundary-logging",
	"broad-except-swallow",
	"conditional-assertion",
	"deep-nesting",
	"deprecated-pattern",
	"dead-code",
	"direct-get-logger",
	"duplicate-call-sequence",
	"eager-test",
	"feature-envy",
	"fixture-outside-conftest",
	"flat-sibling-files",
	"god-class",
	"hand-built-test-payload",
	"high-complexity",
	"hypothesis-candidate",
	"import-alias",
	"import-fanout",
	"langgraph-deprecated-api",
	"langgraph-state-mutation",
	"langgraph-state-reducer",
	"long-line",
	"long-method",
	"long-test",
	"missing-integration-test",
	"mock-theater",
	"mocked-integration-test",
	"obsolete-or-deprecated-test",
	"oversized-module",
	"oversized-module-soft",
	"python-parse-error",
	"private-import-chain",
	"pytest-asyncio-pattern",
	"repeated-code-block",
	"repeated-magic-number",
	"repeated-string-literal",
	"schema-bypass-test-data",
	"semantic-clone",
	"silent-datetime-fallback",
	"silent-except",
	"too-many-params",
	"type-suppression",
	"unnecessary-wrapper",
	"untested-production-code",
	"weak-test-assertion",
	"wrong-logger-name",
] as const;

const CLI_RULE_ID_SET = new Set<string>(CLI_RULE_IDS);
const CLI_EXECUTABLE_REGEX_TARGETS = new Set<string>(["content", "path"]);
const CLI_DEFAULT_OFF_RULE_IDS = new Set<string>([
	"dead-code",
	"boundary-logging",
	"feature-envy",
	"flat-sibling-files",
	"import-alias",
	"import-fanout",
	"langgraph-deprecated-api",
	"langgraph-state-mutation",
	"langgraph-state-reducer",
	"private-import-chain",
	"pytest-asyncio-pattern",
]);

const CLI_CATEGORY = { label: "CLI · Batch lint", emoji: "🧪" };
const COMMAND_ONLY_RULE_PREFIXES = [
	"GIT-",
	"REMIND-",
	"PY-SHELL-",
	"SHELL-",
] as const;
const CONFIG_SAFETY_RULE_PREFIXES = [
	"BASELINE-",
	"CONFIG-",
	"FE-LINTER-",
	"PY-LINTER-",
	"QA-PATH-",
	"WARN-BASELINE-",
] as const;
const SESSION_LIFECYCLE_RULE_PREFIXES = [
	"BUILTIN-ENFORCE-FULL-READ",
	"BUILTIN-INJECT-PROMPT",
	"REPO-ENROLL-",
	"SESSION-",
	"STOP-",
	"WARN-LARGE-",
] as const;

function hasAnyPrefix(rule_id: string, prefixes: readonly string[]): boolean {
	return prefixes.some((prefix) => rule_id.startsWith(prefix));
}

function cliUnsupportedReason(
	rule_id: string,
	regexRule?: { target: string },
): string {
  if (regexRule?.target === "command") return "command only";
	if (rule_id === "BUILTIN-PROTECTED-PATHS") return "protected mutation";
	if (hasAnyPrefix(rule_id, CONFIG_SAFETY_RULE_PREFIXES)) return "config safety";
	if (hasAnyPrefix(rule_id, COMMAND_ONLY_RULE_PREFIXES)) return "command only";
	if (hasAnyPrefix(rule_id, SESSION_LIFECYCLE_RULE_PREFIXES)) {
		return "session lifecycle";
	}
	return "runtime payload";
}

function formatCliTitle(rule_id: string): string {
	return rule_id
		.split("-")
		.map((word) => word.charAt(0).toUpperCase() + word.slice(1))
		.join(" ");
}

function directHookRuleCliCounterparts(
	config: SlopgateConfig,
): Record<string, string[]> {
	return Object.fromEntries(
		Object.entries(config.rule_counterparts).filter(
			([rule_id]) => rule_id !== QUALITY_LINT_RULE_ID,
		),
	);
}

function hookCounterpartsForCli(
	rule_id: string,
	counterparts: Record<string, string[]>,
): string[] {
	return Object.entries(counterparts)
		.filter(([_hookRuleId, cliRuleIds]) => cliRuleIds.includes(rule_id))
		.map(([hookRuleId]) => hookRuleId);
}

function surfaceHookEnabled(
	config: SlopgateConfig,
	rule_id: string,
): boolean {
	const surfaceEnabled = config.rule_surfaces[rule_id]?.hook?.enabled;
	if (surfaceEnabled !== undefined) return surfaceEnabled;
	const enabledVal = config.enabled_rules[rule_id];
	return enabledVal === undefined ? true : Boolean(enabledVal);
}

function surfaceCliEnabled(
	config: SlopgateConfig,
	rule_id: string,
	cliCounterparts: string[],
	defaultEnabled: boolean,
): { enabled: boolean; partiallyEnabled: boolean } {
	const surfaceEnabled = config.rule_surfaces[rule_id]?.cli?.enabled;
	if (surfaceEnabled !== undefined) {
		return { enabled: surfaceEnabled, partiallyEnabled: false };
	}
	const cliStates = cliCounterparts.map(
		(cliRuleId) => config.enabled_cli_rules[cliRuleId] ?? defaultEnabled,
	);
	const enabled =
		cliStates.length > 0 ? cliStates.every(Boolean) : defaultEnabled;
	return {
		enabled,
		partiallyEnabled: cliStates.some(Boolean) && !enabled,
	};
}

function hookEventsForRule(config: SlopgateConfig, rule_id: string): string[] {
	return config.rule_surfaces[rule_id]?.hook?.events ?? [];
}

// ── Category grouping ────────────────────────────────────────────────────────
const CATEGORY_MAP: Array<{
	prefix: string | string[];
	label: string;
	emoji: string;
}> = [
	{ prefix: "BUILTIN", label: "Infrastructure", emoji: "🏗️" },
	{ prefix: "GLOBAL", label: "Global", emoji: "🌐" },
	{
		prefix: ["PY-CODE", "PY-EXC", "PY-LOG", "PY-TYPE", "PY-SHELL"],
		label: "Python · Code",
		emoji: "🐍",
	},
	{
		prefix: ["PY-QUALITY", "PY-TEST", "PY-LINTER"],
		label: "Python · Quality",
		emoji: "✅",
	},
	{ prefix: ["TS", "FE"], label: "TypeScript / Frontend", emoji: "⚡" },
	{ prefix: "RS", label: "Rust", emoji: "🦀" },
	{ prefix: "GIT", label: "Git", emoji: "📦" },
	{ prefix: ["SHELL", "QA"], label: "Shell / QA", emoji: "🐚" },
	{ prefix: ["WARN", "STOP"], label: "Warnings / Stop", emoji: "⚠️" },
	{ prefix: ["SESSION", "CONFIG"], label: "Session / Config", emoji: "⚙️" },
	{ prefix: ["STYLE", "REMIND"], label: "Style / Reminders", emoji: "💅" },
];

function getCategory(rule_id: string): { label: string; emoji: string } {
	if (CLI_RULE_ID_SET.has(rule_id)) return CLI_CATEGORY;
	for (const { prefix, label, emoji } of CATEGORY_MAP) {
		const prefixes = Array.isArray(prefix) ? prefix : [prefix];
		if (prefixes.some((p) => rule_id.startsWith(p))) return { label, emoji };
	}
	return { label: "Other", emoji: "📋" };
}

function categorySortIndex(label: string): number {
	if (label === CLI_CATEGORY.label) return CATEGORY_MAP.length;
	const index = CATEGORY_MAP.findIndex((c) => c.label === label);
	return index === -1 ? CATEGORY_MAP.length + 1 : index;
}

// ── Build rule metadata list from config ────────────────────────────────────
function buildRuleMetadata(
	config: SlopgateConfig,
	fireCounts: Map<string, number>,
): RuleMetadata[] {
	const regexMap = new Map(config.regex_rules.map((r) => [r.rule_id, r]));
	const directCounterparts = directHookRuleCliCounterparts(config);
	const directCliCounterpartIds = new Set<string>(
		Object.values(directCounterparts).flat(),
	);
	const hookRuleIds = new Set<string>([
		...Object.keys(config.enabled_rules),
		...Object.keys(config.rule_surfaces).filter(
			(ruleId) => !CLI_RULE_ID_SET.has(ruleId),
		),
		...config.regex_rules.map((r) => r.rule_id),
	]);
	const cliRuleIds = new Set<string>([
		...CLI_RULE_IDS,
		...Object.keys(config.enabled_cli_rules),
		...Object.keys(config.rule_surfaces).filter((ruleId) =>
			CLI_RULE_ID_SET.has(ruleId),
		),
	]);

	const hookRules = [...hookRuleIds].map((rule_id) => {
		const regexRule = regexMap.get(rule_id);
		const hookEnabled = surfaceHookEnabled(config, rule_id);
		const cliCounterparts = directCounterparts[rule_id] ?? [];
		const regexCliExecutable =
			regexRule !== undefined &&
			CLI_EXECUTABLE_REGEX_TARGETS.has(regexRule.target);
		const cliRuleIds =
			cliCounterparts.length > 0
				? cliCounterparts
				: regexCliExecutable
					? [rule_id]
					: [];
		const { enabled: cliEnabled, partiallyEnabled: cliPartiallyEnabled } =
			surfaceCliEnabled(
				config,
				rule_id,
				cliRuleIds,
				cliCounterparts.length > 0 &&
					cliRuleIds.every((cliRuleId) => !CLI_DEFAULT_OFF_RULE_IDS.has(cliRuleId)),
			);
		const hookAction =
			config.rule_surfaces[rule_id]?.hook?.action ?? regexRule?.action ?? "deny";
		const hookEvents = hookEventsForRule(config, rule_id);

		return {
			rule_id,
			title: regexRule?.title ?? rule_id,
			description:
				getRuleDescription(rule_id) ?? regexRule?.message?.split("\n")[0] ?? "",
			severity: (regexRule?.severity ?? "MEDIUM") as Severity,
			category: getCategory(rule_id).label,
			source: regexRule ? "regex" : "builtin",
			enabled: hookEnabled || cliEnabled || cliPartiallyEnabled,
			hookSupported: true,
			cliSupported: cliRuleIds.length > 0,
			hookEnabled,
			cliEnabled,
			cliPartiallyEnabled,
			cliUnsupportedReason:
				cliRuleIds.length > 0
					? undefined
					: cliUnsupportedReason(rule_id, regexRule),
			fireCount:
				(fireCounts.get(rule_id) ?? 0) +
				cliCounterparts.reduce(
					(total, cliRuleId) => total + (fireCounts.get(cliRuleId) ?? 0),
					0,
				),
			action: hookAction as RuleMetadata["action"],
			hookAction: hookAction as RuleSurfaceAction,
			hookEvents,
			path_globs: regexRule?.path_globs ?? [],
			exclude_path_globs: regexRule?.exclude_path_globs ?? [],
			events: regexRule?.events ?? [],
			cliRuleIds,
			cliCounterparts,
			hookCounterparts: [],
		} satisfies RuleMetadata;
	});

	const cliRules = [...cliRuleIds]
		.filter((rule_id) => !directCliCounterpartIds.has(rule_id))
		.map((rule_id) => {
			const surfaceEnabled = config.rule_surfaces[rule_id]?.cli?.enabled;
			const enabledVal = config.enabled_cli_rules[rule_id];
			const cliEnabled =
				surfaceEnabled ??
				(enabledVal === undefined
					? !CLI_DEFAULT_OFF_RULE_IDS.has(rule_id)
					: Boolean(enabledVal));

			return {
				rule_id,
				title: formatCliTitle(rule_id),
				description: "CLI lint collector used by slopgate lint.",
				severity: "MEDIUM" as Severity,
				category: CLI_CATEGORY.label,
				source: "cli",
				enabled: cliEnabled,
				hookSupported: false,
				cliSupported: true,
				hookEnabled: true,
				cliEnabled,
				cliPartiallyEnabled: false,
				hookUnsupportedReason: "source lint available",
				fireCount: fireCounts.get(rule_id) ?? 0,
				action: "lint",
				hookAction: "deny",
				hookEvents: [],
				path_globs: [],
				exclude_path_globs: [],
				events: ["slopgate lint"],
				cliRuleIds: [rule_id],
				cliCounterparts: [],
				hookCounterparts: hookCounterpartsForCli(rule_id, directCounterparts),
			} satisfies RuleMetadata;
		});

	return [...hookRules, ...cliRules].sort((a, b) => {
		// Sort by category order, then alphabetically
		const catA = categorySortIndex(a.category);
		const catB = categorySortIndex(b.category);
		if (catA !== catB) return catA - catB;
		return a.rule_id.localeCompare(b.rule_id);
	});
}

// ── Global skip_paths editor ─────────────────────────────────────────────────
const GlobalSkipPathsEditor = memo(function GlobalSkipPathsEditor() {
	const { config, setSkipPaths } = useRulesConfig();
	const [draft, setDraft] = useState("");
	const paths = useMemo(() => config.skip_paths ?? [], [config.skip_paths]);

	const add = useCallback(() => {
		const p = draft.trim();
		if (!p || paths.includes(p)) return;
		setSkipPaths([...paths, p]);
		setDraft("");
	}, [draft, paths, setSkipPaths]);

	const remove = useCallback(
		(p: string) => {
			setSkipPaths(paths.filter((x) => x !== p));
		},
		[paths, setSkipPaths],
	);

	return (
		<div className="border border-border rounded-md bg-card/30 p-3 space-y-2">
			<div className="flex items-center gap-2">
				<Globe className="w-3.5 h-3.5 text-muted-foreground" />
				<span className="text-xs font-medium">Global skip_paths</span>
				<span className="text-[10px] text-muted-foreground">
					— suppresses repo-strict/project rules for matching paths; always-on
					safety still runs
				</span>
			</div>
			<div className="flex flex-wrap gap-1.5 min-h-[24px]">
				{paths.length === 0 && (
					<span className="text-[10px] text-muted-foreground/50 italic">
						no global exclusions
					</span>
				)}
				{paths.map((p) => (
					<span
						key={p}
						className="flex items-center gap-1 px-2 py-0.5 bg-muted rounded text-[10px] font-mono"
					>
						{p}
						<button
							type="button"
							onClick={() => remove(p)}
							className="hover:text-signal-block ml-1"
						>
							<X className="w-2.5 h-2.5" />
						</button>
					</span>
				))}
			</div>
			<div className="flex gap-1.5 max-w-sm">
				<Input
					value={draft}
					onChange={(e) => setDraft(e.target.value)}
					onKeyDown={(e) => e.key === "Enter" && add()}
					placeholder="src/legacy/** or **/generated/**"
					className="h-6 text-[10px] font-mono bg-background"
				/>
				<button
					type="button"
					onClick={add}
					disabled={!draft.trim()}
					className="flex items-center gap-1 px-2 py-0.5 text-[10px] rounded bg-primary/10 text-primary border border-primary/20 hover:bg-primary/20 disabled:opacity-40 transition-colors whitespace-nowrap"
				>
					<Plus className="w-3 h-3" /> Add
				</button>
			</div>
		</div>
	);
});

// ── Summary cards ────────────────────────────────────────────────────────────
const SummaryCards = memo(function SummaryCards({
	rules,
}: {
	rules: RuleMetadata[];
}) {
	const total = rules.length;
	const hookEnabled = rules.filter(
		(r) => r.hookSupported && r.hookEnabled,
	).length;
	const hookDisabled = rules.filter(
		(r) => r.hookSupported && !r.hookEnabled,
	).length;
	const cliEnabled = rules.filter((r) => r.cliSupported && r.cliEnabled).length;
	const cliDisabled = rules.filter(
		(r) => r.cliSupported && !r.cliEnabled,
	).length;
	const active = rules.filter((r) => r.enabled && r.fireCount > 0).length;

	return (
		<div className="grid grid-cols-5 gap-2">
			{[
				{ label: "Total Rules", value: total, color: "text-foreground" },
				{
					label: "Hook On / Off",
					value: `${hookEnabled}/${hookDisabled}`,
					color: "text-signal-allow",
				},
				{
					label: "CLI On / Off",
					value: `${cliEnabled}/${cliDisabled}`,
					color: "text-primary",
				},
				{ label: "Active (fired)", value: active, color: "text-signal-ask" },
				{
					label: "Disabled Total",
					value: hookDisabled + cliDisabled,
					color: "text-muted-foreground/60",
				},
			].map(({ label, value, color }) => (
				<div
					key={label}
					className="px-3 py-2.5 rounded-md border border-border bg-card text-center"
				>
					<div className={cn("text-xl font-semibold leading-tight", color)}>
						{value}
					</div>
					<div className="text-[10px] text-muted-foreground uppercase tracking-wider mt-0.5">
						{label}
					</div>
				</div>
			))}
		</div>
	);
});

const SurfaceSwitch = memo(function SurfaceSwitch({
	label,
	supported,
	checked,
	onToggle,
	unsupportedLabel,
}: {
	label: string;
	supported: boolean;
	checked: boolean;
	onToggle: () => void;
	unsupportedLabel: string;
}) {
	if (!supported) {
		return (
			<span
				className="inline-flex items-center rounded border border-border/40 px-1.5 py-0.5 text-[9px] text-muted-foreground/50"
				title={`${label} is not available: ${unsupportedLabel}`}
			>
				{unsupportedLabel}
			</span>
		);
	}
	return (
		<Switch
			aria-label={label}
			checked={checked}
			onCheckedChange={onToggle}
			className="scale-75 origin-left"
		/>
	);
});

// ── Exclusion editor (inline) ────────────────────────────────────────────────
const ExclusionEditor = memo(function ExclusionEditor({
	globs,
	onChange,
	readOnly,
}: {
	globs: string[];
	onChange: (globs: string[]) => void;
	readOnly: boolean;
}) {
	const [draft, setDraft] = useState("");

	const add = useCallback(() => {
		const g = draft.trim();
		if (!g || globs.includes(g)) return;
		onChange([...globs, g]);
		setDraft("");
	}, [draft, globs, onChange]);

	const remove = useCallback(
		(g: string) => {
			onChange(globs.filter((x) => x !== g));
		},
		[globs, onChange],
	);

	return (
		<div className="space-y-1.5">
			<div className="text-[10px] text-muted-foreground uppercase tracking-wider">
				Path exclusions (exclude_path_globs)
			</div>
			<div className="flex flex-wrap gap-1.5 min-h-[24px]">
				{globs.length === 0 && (
					<span className="text-[10px] text-muted-foreground/50 italic">
						no exclusions
					</span>
				)}
				{globs.map((g) => (
					<span
						key={g}
						className="flex items-center gap-1 px-2 py-0.5 bg-muted rounded text-[10px] font-mono"
					>
						{g}
						{!readOnly && (
							<button
								type="button"
								onClick={() => remove(g)}
								className="hover:text-signal-block ml-1"
							>
								<X className="w-2.5 h-2.5" />
							</button>
						)}
					</span>
				))}
			</div>
			{!readOnly && (
				<div className="flex gap-1.5 max-w-sm">
					<Input
						value={draft}
						onChange={(e) => setDraft(e.target.value)}
						onKeyDown={(e) => e.key === "Enter" && add()}
						placeholder="**/tests/** or src/legacy/**"
						className="h-6 text-[10px] font-mono bg-background"
					/>
					<button
						type="button"
						onClick={add}
						disabled={!draft.trim()}
						className="flex items-center gap-1 px-2 py-0.5 text-[10px] rounded bg-primary/10 text-primary border border-primary/20 hover:bg-primary/20 disabled:opacity-40 transition-colors whitespace-nowrap"
					>
						<Plus className="w-3 h-3" /> Add
					</button>
				</div>
			)}
			{readOnly && (
				<div className="text-[10px] text-muted-foreground/50 italic">
					Exclusions only apply to regex rules. Global skip_paths suppress
					repo-strict/project rules; always-on safety still runs.
				</div>
			)}
		</div>
	);
});

// ── Individual rule row ───────────────────────────────────────────────────────
const RuleRow = memo(function RuleRow({
	rule,
	onSetHookSurface,
	onSetRuleCliSurface,
	onExclusionsChange,
}: {
	rule: RuleMetadata;
	onSetHookSurface: (id: string, hook: RuleHookSurface) => void;
	onSetRuleCliSurface: (
		id: string,
		cliRuleIds: string[],
		enabled: boolean,
	) => void;
	onExclusionsChange: (id: string, globs: string[]) => void;
}) {
	const [expanded, setExpanded] = useState(false);
	const sevColor = SEVERITY_COLORS[rule.severity] ?? "hsl(210,20%,55%)";
	const toggleEvent = useCallback(
		(eventName: string) => {
			const events = new Set(rule.hookEvents);
			if (events.has(eventName)) events.delete(eventName);
			else events.add(eventName);
			onSetHookSurface(rule.rule_id, { events: [...events].sort() });
		},
		[onSetHookSurface, rule.hookEvents, rule.rule_id],
	);

	const actionBadge: Record<string, string> = {
		deny: "bg-signal-block/20 text-signal-block",
		block: "bg-signal-block/20 text-signal-block",
		warn: "bg-signal-warn/20 text-signal-warn",
		ask: "bg-signal-ask/20 text-signal-ask",
		allow: "bg-signal-allow/20 text-signal-allow",
		context: "bg-muted text-muted-foreground",
		lint: "bg-primary/10 text-primary",
	};

	return (
		<>
			<tr
				className={cn(
					"border-b border-border/30 hover:bg-muted/10 transition-colors",
					!rule.enabled && "opacity-50",
					expanded && "bg-muted/5",
				)}
			>
				{/* expand chevron */}
				<td className="px-2 py-2 w-6">
					<button type="button" onClick={() => setExpanded((e) => !e)}>
						{expanded ? (
							<ChevronDown className="w-3 h-3 text-muted-foreground" />
						) : (
							<ChevronRight className="w-3 h-3 text-muted-foreground" />
						)}
					</button>
				</td>
				{/* hook toggle */}
				<td className="px-2 py-2">
					<SurfaceSwitch
						label={`${rule.rule_id} hook enablement`}
						supported={rule.hookSupported}
						checked={rule.hookEnabled}
						unsupportedLabel={rule.hookUnsupportedReason ?? "cli only"}
						onToggle={() =>
							onSetHookSurface(rule.rule_id, { enabled: !rule.hookEnabled })
						}
					/>
				</td>
				{/* CLI toggle */}
				<td className="px-2 py-2">
					<SurfaceSwitch
						label={`${rule.rule_id} CLI enablement`}
						supported={rule.cliSupported}
						checked={rule.cliEnabled}
						unsupportedLabel={rule.cliUnsupportedReason ?? "hook only"}
						onToggle={() =>
							onSetRuleCliSurface(
								rule.rule_id,
								rule.cliRuleIds,
								!rule.cliEnabled,
							)
						}
					/>
				</td>
				{/* rule id */}
				<td className="px-2 py-2 font-mono text-xs">
					<button
						type="button"
						className="font-mono text-left"
						onClick={() => setExpanded((e) => !e)}
						style={{ color: sevColor }}
					>
						{rule.rule_id}
					</button>
				</td>
				{/* title */}
				<td className="px-2 py-2 text-xs text-muted-foreground max-w-[220px] truncate">
					<button
						type="button"
						className="max-w-full truncate text-left"
						onClick={() => setExpanded((e) => !e)}
					>
						{rule.title !== rule.rule_id
							? rule.title
							: rule.description.slice(0, 60) || "—"}
					</button>
				</td>
				{/* severity */}
				<td className="px-2 py-2">
					<span
						className="text-[9px] px-1.5 py-0.5 rounded font-medium uppercase"
						style={{
							backgroundColor: `${sevColor}20`,
							color: sevColor,
						}}
					>
						{rule.severity}
					</span>
				</td>
				{/* action */}
				<td className="px-2 py-2">
					<span
						className={cn(
							"text-[9px] px-1.5 py-0.5 rounded uppercase",
							actionBadge[rule.action] ?? "bg-muted text-muted-foreground",
						)}
					>
						{rule.action}
					</span>
				</td>
				{/* source */}
				<td className="px-2 py-2">
					<span className="text-[9px] text-muted-foreground">
						{rule.source}
					</span>
				</td>
				{/* fire count */}
				<td className="px-2 py-2 text-right">
					<span
						className={cn(
							"text-xs font-mono",
							rule.fireCount > 0
								? "text-signal-ask font-semibold"
								: "text-muted-foreground/40",
						)}
					>
						{rule.fireCount > 0 ? rule.fireCount : "—"}
					</span>
				</td>
				{/* exclusions button — always visible for regex rules */}
				<td className="px-2 py-2 text-right">
					{rule.source === "regex" ? (
						<button
							type="button"
							onClick={(e) => {
								e.stopPropagation();
								setExpanded((ex) => !ex);
							}}
							title={
								rule.exclude_path_globs.length > 0
									? `${rule.exclude_path_globs.length} path exclusion(s) — click to edit`
									: "Add path exclusions"
							}
							className={cn(
								"text-[10px] px-1.5 py-0.5 rounded border transition-colors",
								rule.exclude_path_globs.length > 0
									? "bg-signal-ask/10 text-signal-ask border-signal-ask/20 hover:bg-signal-ask/20"
									: "text-muted-foreground/50 border-border/50 hover:text-primary hover:border-primary/30 hover:bg-primary/5",
							)}
						>
							{rule.exclude_path_globs.length > 0
								? `${rule.exclude_path_globs.length} excl.`
								: "+ excl."}
						</button>
					) : (
						<span
							className="text-[10px] text-muted-foreground/50 border border-border/40 px-1.5 py-0.5 rounded cursor-default"
							title="Builtin rules are not editable here; global skip_paths only suppress repo-strict/project checks, not always-on safety"
						>
							global ↗
						</span>
					)}
				</td>
			</tr>
			{expanded && (
				<tr className="border-b border-border/20 bg-muted/5">
					<td colSpan={TABLE_COLSPAN} className="px-8 py-3 space-y-3">
						{/* description */}
						{rule.description && (
							<div className="text-xs text-muted-foreground max-w-2xl leading-relaxed">
								{rule.description}
							</div>
						)}
						<div className="flex flex-wrap gap-2 text-[10px] text-muted-foreground">
							{rule.hookSupported && (
								<span
									className={cn(
										"px-1.5 py-0.5 rounded border",
										rule.hookEnabled
											? "border-signal-allow/25 bg-signal-allow/10 text-signal-allow"
											: "border-border bg-muted/40",
									)}
								>
									Hook runtime {rule.hookEnabled ? "enabled" : "disabled"}
								</span>
							)}
							{rule.cliSupported && (
								<span
									className={cn(
										"px-1.5 py-0.5 rounded border",
										rule.cliEnabled || rule.cliPartiallyEnabled
											? "border-primary/25 bg-primary/10 text-primary"
											: "border-border bg-muted/40",
									)}
								>
									CLI lint{" "}
									{rule.cliPartiallyEnabled
										? "partially enabled"
										: rule.cliEnabled
											? "enabled"
											: "disabled"}
								</span>
							)}
							{rule.cliCounterparts.length > 0 && (
								<span className="px-1.5 py-0.5 rounded border border-border bg-muted/30">
									CLI checks: {rule.cliCounterparts.join(", ")}
								</span>
							)}
							{rule.hookCounterparts.length > 0 && (
								<span className="px-1.5 py-0.5 rounded border border-border bg-muted/30">
									Hook counterparts: {rule.hookCounterparts.join(", ")}
								</span>
							)}
						</div>
						{rule.hookSupported && (
							<div className="grid gap-3 sm:grid-cols-[180px_1fr]">
								<div className="space-y-1">
									<div className="text-[10px] text-muted-foreground uppercase tracking-wider">
										Hook action
									</div>
									<select
										value={rule.hookAction}
										onChange={(event) =>
											onSetHookSurface(rule.rule_id, {
												action: event.target.value as RuleSurfaceAction,
											})
										}
										className="h-7 w-full rounded border border-border bg-background px-2 text-[11px] font-mono text-foreground"
									>
										{HOOK_ACTIONS.map((action) => (
											<option key={action} value={action}>
												{action}
											</option>
										))}
									</select>
								</div>
								<div className="space-y-1">
									<div className="text-[10px] text-muted-foreground uppercase tracking-wider">
										Hook events
									</div>
									<div className="flex flex-wrap gap-1.5">
										{HOOK_EVENT_OPTIONS.map((eventName) => {
											const checked = rule.hookEvents.includes(eventName);
											return (
												<button
													key={eventName}
													type="button"
													onClick={() => toggleEvent(eventName)}
													className={cn(
														"rounded border px-2 py-1 text-[10px] font-mono transition-colors",
														checked
															? "border-primary/35 bg-primary/15 text-primary"
															: "border-border bg-muted/20 text-muted-foreground hover:bg-muted/40",
													)}
												>
													{eventName}
												</button>
											);
										})}
										{rule.hookEvents.length > 0 && (
											<button
												type="button"
												onClick={() =>
													onSetHookSurface(rule.rule_id, { events: [] })
												}
												className="rounded border border-border bg-muted/20 px-2 py-1 text-[10px] text-muted-foreground hover:bg-muted/40"
											>
												Clear
											</button>
										)}
									</div>
								</div>
							</div>
						)}
						{/* exclusions FIRST — most likely reason to expand */}
						<ExclusionEditor
							globs={rule.exclude_path_globs}
							onChange={(globs) => onExclusionsChange(rule.rule_id, globs)}
							readOnly={rule.source !== "regex"}
						/>
						{/* path globs (applies-to) */}
						{rule.path_globs.length > 0 && (
							<div className="space-y-1">
								<div className="text-[10px] text-muted-foreground uppercase tracking-wider">
									Applies to
								</div>
								<div className="flex flex-wrap gap-1">
									{rule.path_globs.map((g) => (
										<span
											key={g}
											className="px-1.5 py-0.5 bg-muted rounded text-[10px] font-mono text-muted-foreground"
										>
											{g}
										</span>
									))}
								</div>
							</div>
						)}
					</td>
				</tr>
			)}
		</>
	);
});

// ── Category group ────────────────────────────────────────────────────────────
const CategoryGroup = memo(function CategoryGroup({
	label,
	emoji,
	rules,
	onSetHookSurface,
	onSetRuleCliSurface,
	onExclusionsChange,
}: {
	label: string;
	emoji: string;
	rules: RuleMetadata[];
	onSetHookSurface: (id: string, hook: RuleHookSurface) => void;
	onSetRuleCliSurface: (
		id: string,
		cliRuleIds: string[],
		enabled: boolean,
	) => void;
	onExclusionsChange: (id: string, globs: string[]) => void;
}) {
	const active = rules.filter((r) => r.enabled && r.fireCount > 0).length;
	const [open, setOpen] = useState(active > 0);

	const totalFires = rules.reduce((s, r) => s + r.fireCount, 0);
	const disabled = rules.filter((r) => !r.enabled).length;

	return (
		<>
			<tr
				className="border-b border-border/50 bg-card/50 cursor-pointer select-none hover:bg-muted/20"
				onClick={() => setOpen((o) => !o)}
			>
				<td colSpan={TABLE_COLSPAN} className="px-3 py-2">
					<div className="flex items-center gap-2">
						{open ? (
							<ChevronDown className="w-3.5 h-3.5 text-muted-foreground" />
						) : (
							<ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />
						)}
						<span className="text-xs font-semibold">
							{emoji} {label}
						</span>
						<span className="text-[10px] text-muted-foreground ml-1">
							{rules.length} rules
						</span>
						{active > 0 && (
							<span className="text-[10px] px-1.5 py-0.5 rounded bg-signal-ask/20 text-signal-ask">
								{active} active · {totalFires} fires
							</span>
						)}
						{disabled > 0 && (
							<span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
								{disabled} disabled
							</span>
						)}
					</div>
				</td>
			</tr>
			{open &&
				rules.map((rule) => (
					<RuleRow
						key={rule.rule_id}
						rule={rule}
						onSetHookSurface={onSetHookSurface}
						onSetRuleCliSurface={onSetRuleCliSurface}
						onExclusionsChange={onExclusionsChange}
					/>
				))}
		</>
	);
});

// ── Save toolbar ──────────────────────────────────────────────────────────────
const SaveToolbar = memo(function SaveToolbar() {
	const {
		pendingCount,
		saveConfig,
		discardChanges,
		saveStatus,
		saveError,
		apiAvailable,
		loading,
	} = useRulesConfig();

	if (loading) return null;

	return (
		<div
			className={cn(
				"flex items-center gap-3 px-3 py-2 rounded-md border text-xs transition-all",
				pendingCount > 0
					? "border-signal-ask/30 bg-signal-ask/5"
					: "border-border bg-card/30",
			)}
		>
			{/* API indicator */}
			<span
				className={cn(
					"flex items-center gap-1 text-[10px]",
					apiAvailable ? "text-signal-allow" : "text-muted-foreground",
				)}
			>
				{apiAvailable ? (
					<Wifi className="w-3 h-3" />
				) : (
					<WifiOff className="w-3 h-3" />
				)}
				{apiAvailable ? "API connected" : "read-only (no API)"}
			</span>

			<span className="text-muted-foreground">·</span>

			{pendingCount > 0 ? (
				<>
					<span className="text-signal-ask font-medium">
						{pendingCount} unsaved change{pendingCount !== 1 ? "s" : ""}
					</span>
					<button
						type="button"
						onClick={() => saveConfig()}
						disabled={saveStatus === "saving" || !apiAvailable}
						className="flex items-center gap-1 px-2 py-1 rounded bg-signal-allow/20 text-signal-allow border border-signal-allow/30 hover:bg-signal-allow/30 disabled:opacity-50 transition-colors"
					>
						{saveStatus === "saving" ? (
							<Loader2 className="w-3 h-3 animate-spin" />
						) : (
							<Save className="w-3 h-3" />
						)}
						Save to Littlebox
					</button>
					<button
						type="button"
						onClick={discardChanges}
						className="flex items-center gap-1 px-2 py-1 rounded text-muted-foreground hover:bg-muted transition-colors"
					>
						<RotateCcw className="w-3 h-3" /> Discard
					</button>
				</>
			) : (
				<span className="text-muted-foreground">
					{saveStatus === "saved" ? (
						<span className="text-signal-allow flex items-center gap-1">
							<Check className="w-3 h-3" /> Saved
						</span>
					) : (
						"No pending changes"
					)}
				</span>
			)}

			{saveStatus === "error" && saveError && (
				<span className="text-signal-block text-[10px] flex items-center gap-1">
					<AlertTriangle className="w-3 h-3" /> {saveError}
				</span>
			)}
		</div>
	);
});

// ── Main component ────────────────────────────────────────────────────────────
export function RuleManager({ fireCounts }: Props) {
	const {
		config,
		setRuleHookSurface,
		setRuleCliSurface,
		setExclusions,
		loading,
	} = useRulesConfig();
	const [search, setSearch] = useState("");
	const [filter, setFilter] = useState<
		"all" | "active" | "dormant" | "disabled"
	>("all");

	const allRules = useMemo(
		() => buildRuleMetadata(config, fireCounts),
		[config, fireCounts],
	);

	const filtered = useMemo(() => {
		let rules = allRules;
		if (filter === "active")
			rules = rules.filter((r) => r.enabled && r.fireCount > 0);
		else if (filter === "dormant")
			rules = rules.filter((r) => r.enabled && r.fireCount === 0);
		else if (filter === "disabled") rules = rules.filter((r) => !r.enabled);
		if (search) {
			const q = search.toLowerCase();
			rules = rules.filter(
				(r) =>
					r.rule_id.toLowerCase().includes(q) ||
					r.title.toLowerCase().includes(q) ||
					r.description.toLowerCase().includes(q) ||
					r.cliCounterparts.some((id) => id.toLowerCase().includes(q)) ||
					r.hookCounterparts.some((id) => id.toLowerCase().includes(q)),
			);
		}
		return rules;
	}, [allRules, filter, search]);

	const grouped = useMemo(() => {
		const map = new Map<string, { emoji: string; rules: RuleMetadata[] }>();
		for (const rule of filtered) {
			const cat = getCategory(rule.rule_id);
			if (!map.has(cat.label))
				map.set(cat.label, { emoji: cat.emoji, rules: [] });
			map.get(cat.label)?.rules.push(rule);
		}
		// Sort groups by category order
		return [...map.entries()].sort(([a], [b]) => {
			return categorySortIndex(a) - categorySortIndex(b);
		});
	}, [filtered]);

	const setRuleCliEnabled = useCallback(
		(rule_id: string, cliRuleIds: string[], enabled: boolean) => {
			setRuleCliSurface(rule_id, cliRuleIds, { enabled });
		},
		[setRuleCliSurface],
	);

	if (loading) {
		return (
			<div className="flex items-center justify-center py-16 text-muted-foreground gap-2">
				<Loader2 className="w-4 h-4 animate-spin" />
				<span className="text-xs">Loading rule configuration…</span>
			</div>
		);
	}

	if (allRules.length === 0) {
		return (
			<div className="flex flex-col items-center justify-center py-16 text-muted-foreground gap-2">
				<span className="text-xs">
					No rules found. Check that build-standalone.py was run with --ssh.
				</span>
				<span className="text-[10px]">
					window.__SLOPGATE_CONFIG__ is missing.
				</span>
			</div>
		);
	}

	return (
		<div className="space-y-4">
			{/* Global skip_paths — suppresses repo-strict/project rules; always-on safety still runs */}
			<GlobalSkipPathsEditor />

			{/* Summary */}
			<SummaryCards rules={allRules} />

			{/* Toolbar */}
			<div className="flex items-center gap-3">
				<div className="relative flex-1 max-w-xs">
					<Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3 h-3 text-muted-foreground" />
					<Input
						value={search}
						onChange={(e) => setSearch(e.target.value)}
						placeholder="Search rules…"
						className="pl-7 h-7 text-xs bg-background"
					/>
				</div>
				<div className="flex gap-1">
					{(["all", "active", "dormant", "disabled"] as const).map((f) => (
						<button
							type="button"
							key={f}
							onClick={() => setFilter(f)}
							className={cn(
								"px-2 py-0.5 text-[10px] rounded-sm transition-colors capitalize",
								filter === f
									? "bg-primary text-primary-foreground"
									: "text-muted-foreground hover:bg-muted",
							)}
						>
							{f}
						</button>
					))}
				</div>
				<div className="ml-auto">
					<SaveToolbar />
				</div>
			</div>

			{/* Table */}
			<div className="border border-border rounded-md bg-card/30 overflow-hidden">
				<table className="w-full">
					<thead>
						<tr className="border-b border-border text-muted-foreground text-[10px] uppercase bg-card/50">
							<th className="px-2 py-2 w-6" />
							<th className="px-2 py-2 text-left w-12">Hook</th>
							<th className="px-2 py-2 text-left w-12">CLI</th>
							<th className="px-2 py-2 text-left">Rule ID</th>
							<th className="px-2 py-2 text-left">Title / Description</th>
							<th className="px-2 py-2 text-left w-20">Severity</th>
							<th className="px-2 py-2 text-left w-20">Action</th>
							<th className="px-2 py-2 text-left w-14">Source</th>
							<th className="px-2 py-2 text-right w-16">Fires</th>
							<th className="px-2 py-2 text-right w-20">Exclusions</th>
						</tr>
					</thead>
					<tbody>
						{grouped.length === 0 ? (
							<tr>
								<td
									colSpan={TABLE_COLSPAN}
									className="text-center py-8 text-muted-foreground text-xs"
								>
									No rules match
								</td>
							</tr>
						) : (
							grouped.map(([label, { emoji, rules }]) => (
								<CategoryGroup
									key={label}
									label={label}
									emoji={emoji}
									rules={rules}
									onSetHookSurface={setRuleHookSurface}
									onSetRuleCliSurface={setRuleCliEnabled}
									onExclusionsChange={setExclusions}
								/>
							))
						)}
					</tbody>
				</table>
			</div>

			{/* Footer note */}
			<div className="text-[10px] text-muted-foreground/60 text-center">
				Changes are saved to{" "}
				<code className="font-mono">~/.config/slopgate/config.json</code> on
				Littlebox via SSH. Hook switches affect runtime hook invocation; CLI
				switches affect <code className="font-mono">slopgate lint</code>.
			</div>
		</div>
	);
}
