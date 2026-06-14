import { memo, useCallback, useState, useMemo } from "react";
import { X, Plus, HelpCircle, AlertTriangle } from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
	Sheet,
	SheetContent,
	SheetHeader,
	SheetTitle,
	SheetDescription,
} from "@/components/ui/sheet";
import { cn } from "@/lib/utils";
import type {
	RuleCliSurface,
	RuleHookSurface,
	RuleMetadata,
	RuleSurfaceAction,
} from "@/types/slopgate";
import { SEVERITY_COLORS } from "@/lib/chartTheme";
import { HOOK_ACTIONS, HOOK_EVENT_OPTIONS } from "./model";

interface RuleInspectorProps {
	rule: RuleMetadata | null;
	onSetHookSurface: (id: string, hook: RuleHookSurface) => void;
	onSetRuleCliSurface: (
		id: string,
		cliRuleIds: string[],
		cli: RuleCliSurface,
	) => void;
	onExclusionsChange: (id: string, globs: string[]) => void;
	onClose: () => void;
	isMobile: boolean;
}

interface RuleIdentitySectionProps {
	severity: string;
	source: string;
	title: string;
	description?: string;
	sevColor: string;
}

const RuleIdentitySection = memo(function RuleIdentitySection({
	severity,
	source,
	title,
	description,
	sevColor,
}: RuleIdentitySectionProps) {
	return (
		<div className="space-y-1 pb-3 border-b border-border/60">
			<div className="flex items-center justify-between">
				<Badge
					variant="outline"
					className="text-[0.75rem] px-2 py-0.5 rounded font-medium uppercase border animate-none"
					style={{
						backgroundColor: `${sevColor}15`,
						color: sevColor,
						borderColor: `${sevColor}25`,
					}}
				>
					{severity} Severity
				</Badge>
				<Badge
					variant="outline"
					className="font-mono text-[0.75rem] bg-muted/30 border-transparent text-muted-foreground"
				>
					Source: {source}
				</Badge>
			</div>
			<h3 className="font-semibold text-foreground text-[1.125rem]">{title}</h3>
			{description && (
				<p className="text-muted-foreground text-[0.875rem] leading-relaxed pt-1">
					{description}
				</p>
			)}
		</div>
	);
});

interface PlacementSectionProps {
	ruleId: string;
	hookSupported: boolean;
	hookEnabled: boolean;
	hookUnsupportedReason?: string;
	onSetHookSurface: (id: string, hook: { enabled: boolean }) => void;
	cliSupported: boolean;
	cliEnabled: boolean;
	cliRuleIds: string[];
	cliUnsupportedReason?: string;
	onSetRuleCliSurface: (id: string, cliRuleIds: string[], cli: { enabled: boolean }) => void;
}

const PlacementSection = memo(function PlacementSection({
	ruleId,
	hookSupported,
	hookEnabled,
	hookUnsupportedReason,
	onSetHookSurface,
	cliSupported,
	cliEnabled,
	cliRuleIds,
	cliUnsupportedReason,
	onSetRuleCliSurface,
}: PlacementSectionProps) {
	const handleHookChange = useCallback(() => {
		onSetHookSurface(ruleId, { enabled: !hookEnabled });
	}, [ruleId, hookEnabled, onSetHookSurface]);

	const handleCliChange = useCallback(() => {
		onSetRuleCliSurface(ruleId, cliRuleIds, { enabled: !cliEnabled });
	}, [ruleId, cliRuleIds, cliEnabled, onSetRuleCliSurface]);

	return (
		<div className="space-y-3">
			<h4 className="text-[0.75rem] text-muted-foreground uppercase tracking-wider font-semibold">
				Surface Placement
			</h4>
			<div className="grid grid-cols-1 gap-2.5">
				<div className="flex items-center justify-between p-2.5 rounded bg-muted/20 border border-border/40">
					<div className="flex flex-col">
						<span className="font-medium text-foreground">Hook Placement</span>
						<span className="text-[0.75rem] text-muted-foreground">
							Triggers during live agent tool invocations
						</span>
					</div>
					<div>
						{hookSupported ? (
							<Switch
								aria-label={`${ruleId} hook enablement`}
								checked={hookEnabled}
								onCheckedChange={handleHookChange}
							/>
						) : (
							<Badge variant="secondary" className="text-[0.75rem] px-2 py-0.5 rounded font-normal border-transparent bg-muted/40">
								{hookUnsupportedReason}
							</Badge>
						)}
					</div>
				</div>

				<div className="flex items-center justify-between p-2.5 rounded bg-muted/20 border border-border/40">
					<div className="flex flex-col">
						<span className="font-medium text-foreground">CLI Placement</span>
						<span className="text-[0.75rem] text-muted-foreground">
							Runs inside batch lint and pre-commit scans
						</span>
					</div>
					<div>
						{cliSupported ? (
							<Switch
								aria-label={`${ruleId} CLI enablement`}
								checked={cliEnabled}
								onCheckedChange={handleCliChange}
							/>
						) : (
							<Badge variant="secondary" className="text-[0.75rem] px-2 py-0.5 rounded font-normal border-transparent bg-muted/40">
								{cliUnsupportedReason}
							</Badge>
						)}
					</div>
				</div>
			</div>
		</div>
	);
});

interface HookParamsSectionProps {
	ruleId: string;
	hookAction: RuleSurfaceAction;
	hookEvents: string[];
	onSetHookSurface: (id: string, hook: { action?: RuleSurfaceAction; events?: string[] }) => void;
	onToggleEvent: (eventName: string) => void;
}

const HookParamsSection = memo(function HookParamsSection({
	ruleId,
	hookAction,
	hookEvents,
	onSetHookSurface,
	onToggleEvent,
}: HookParamsSectionProps) {
	const handleActionChange = useCallback((e: React.ChangeEvent<HTMLSelectElement>) => {
		onSetHookSurface(ruleId, { action: e.target.value as RuleSurfaceAction });
	}, [ruleId, onSetHookSurface]);

	return (
		<div className="space-y-3 pt-2">
			<h4 className="text-[0.75rem] text-muted-foreground uppercase tracking-wider font-semibold">
				Hook Parameters
			</h4>
			<div className="space-y-1">
				<label className="text-[0.75rem] text-muted-foreground font-medium">
					Action Enforcement
				</label>
				<select
					value={hookAction}
					onChange={handleActionChange}
					className="h-8 w-full rounded border border-border bg-background px-2.5 text-[0.875rem] text-foreground font-sans focus:outline-none focus:ring-1 focus:ring-primary"
				>
					{HOOK_ACTIONS.map((act) => (
						<option key={act} value={act}>
							{act.toUpperCase()}
						</option>
					))}
				</select>
			</div>

			<div className="space-y-1.5 pt-1">
				<label className="text-[0.75rem] text-muted-foreground font-medium">
					Event Subscription Triggers
				</label>
				<div className="flex flex-wrap gap-1.5">
					{HOOK_EVENT_OPTIONS.map((evtName) => {
						const hasEvent = hookEvents.includes(evtName);
						return (
							<Button
								key={evtName}
								type="button"
								variant={hasEvent ? "secondary" : "outline"}
								size="sm"
								onClick={() => onToggleEvent(evtName)}
								className={cn(
									"h-7 px-2.5 text-[0.75rem] font-mono border transition-all",
									hasEvent && "border-primary bg-primary/10 text-primary hover:bg-primary/20 hover:text-primary font-semibold"
								)}
							>
								{evtName}
							</Button>
						);
					})}
				</div>
			</div>
		</div>
	);
});

interface PathExclusionsSectionProps {
	ruleId: string;
	source: string;
	excludePathGlobs: string[];
	draftExclusion: string;
	onDraftChange: (val: string) => void;
	onAdd: () => void;
	onRemove: (glob: string) => void;
}

const PathExclusionsSection = memo(function PathExclusionsSection({
	ruleId,
	source,
	excludePathGlobs,
	draftExclusion,
	onDraftChange,
	onAdd,
	onRemove,
}: PathExclusionsSectionProps) {
	return (
		<div className="space-y-3 pt-2">
			<h4 className="text-[0.75rem] text-muted-foreground uppercase tracking-wider font-semibold">
				Rule Path Exclusions
			</h4>
			{source === "regex" ? (
				<div className="space-y-2">
					<div className="flex flex-wrap gap-1.5 min-h-[24px]">
						{excludePathGlobs.length === 0 && (
							<span className="text-[0.75rem] text-muted-foreground/70 italic font-medium block py-0.5">
								No exclusions configured for this rule.
							</span>
						)}
						{excludePathGlobs.map((glob) => (
							<Badge
								key={glob}
								variant="outline"
								className="flex items-center gap-1 px-2 py-0.5 bg-muted rounded text-[0.75rem] font-mono border border-border text-foreground transition-all duration-150 animate-in fade-in zoom-in-95 ease-out-quart"
							>
								{glob}
								<Button
									type="button"
									variant="ghost"
									size="icon"
									onClick={() => onRemove(glob)}
									className="h-4 w-4 rounded-full p-0 text-muted-foreground/60 hover:text-signal-block hover:bg-transparent ml-1"
									aria-label={`Remove exclusion ${glob}`}
								>
									<X className="w-3.5 h-3.5" />
								</Button>
							</Badge>
						))}
					</div>
					<div className="flex gap-2">
						<Input
							value={draftExclusion}
							onChange={(e) => onDraftChange(e.target.value)}
							onKeyDown={(e) => e.key === "Enter" && onAdd()}
							placeholder="e.g., **/tests/** or src/legacy/**"
							className="h-8 text-[0.875rem] font-mono bg-background"
						/>
						<Button
							type="button"
							variant="outline"
							size="sm"
							onClick={onAdd}
							disabled={!draftExclusion.trim()}
							className="flex items-center gap-1.5 px-3 h-8 text-[0.875rem] font-medium rounded bg-primary/10 text-primary border border-primary/20 hover:bg-primary/20 disabled:opacity-40 transition-colors whitespace-nowrap"
						>
							<Plus className="w-3.5 h-3.5" /> Add
						</Button>
					</div>
				</div>
			) : (
				<div className="p-2.5 rounded bg-muted/20 border border-border/40 text-[0.75rem] text-muted-foreground leading-normal flex items-start gap-2">
					<AlertTriangle className="w-4 h-4 shrink-0 text-muted-foreground/60" />
					<span>
						Exclusions only apply to regex rules. Global path exclusions suppress repo-strict checks, but always-on safety rules still run.
					</span>
				</div>
			)}
		</div>
	);
});

interface InspectorFooterProps {
	cliCounterparts: string[];
	hookCounterparts: string[];
	effectiveBehaviorSummary: string;
}

const InspectorFooter = memo(function InspectorFooter({
	cliCounterparts,
	hookCounterparts,
	effectiveBehaviorSummary,
}: InspectorFooterProps) {
	return (
		<>
			{(cliCounterparts.length > 0 || hookCounterparts.length > 0) && (
				<div className="space-y-1.5 pt-2 border-t border-border/50 text-[0.75rem] text-muted-foreground">
					{cliCounterparts.length > 0 && (
						<div className="font-mono">
							<Badge variant="outline" className="px-1.5 py-0.5 rounded border border-border bg-muted/30 text-[0.75rem] font-normal text-muted-foreground">
								CLI checks: {cliCounterparts.join(", ")}
							</Badge>
						</div>
					)}
					{hookCounterparts.length > 0 && (
						<div className="font-mono">
							<Badge variant="outline" className="px-1.5 py-0.5 rounded border border-border bg-muted/30 text-[0.75rem] font-normal text-muted-foreground">
								Hook counterparts: {hookCounterparts.join(", ")}
							</Badge>
						</div>
					)}
				</div>
			)}
			<Card className="p-3 bg-card border border-border rounded-md space-y-1 shadow-none">
				<div className="flex items-center gap-1 text-[0.75rem] text-muted-foreground uppercase tracking-wider font-semibold">
					<HelpCircle className="w-3.5 h-3.5" />
					Effective Behavior
				</div>
				<p className="text-[0.75rem] text-muted-foreground leading-relaxed">
					{effectiveBehaviorSummary}
				</p>
			</Card>
		</>
	);
});

function getEffectiveBehavior(rule: RuleMetadata | null): string {
	if (!rule) return "";
	const parts: string[] = [];
	if (rule.hookSupported && rule.hookEnabled) {
		parts.push(`Active on hooks triggering at [${rule.hookEvents.join(", ")}] with action "${rule.hookAction}".`);
	} else if (rule.hookSupported) {
		parts.push("Hook triggers are turned off.");
	} else {
		parts.push(`Hooks are unsupported: ${rule.hookUnsupportedReason}.`);
	}

	if (rule.cliSupported && rule.cliEnabled) {
		parts.push("CLI checker is active for batch execution.");
	} else if (rule.cliSupported) {
		parts.push("CLI checks are inactive.");
	} else {
		parts.push(`CLI checks are unsupported: ${rule.cliUnsupportedReason}.`);
	}

	return parts.join(" ");
}

function useRuleInspectorState(
	rule: RuleMetadata | null,
	onSetHookSurface: (id: string, hook: RuleHookSurface) => void,
	onExclusionsChange: (id: string, globs: string[]) => void,
) {
	const [draftExclusion, setDraftExclusion] = useState("");

	const sevColor = useMemo(() => {
		if (!rule) return "hsl(210,20%,55%)";
		return SEVERITY_COLORS[rule.severity] ?? "hsl(210,20%,55%)";
	}, [rule]);

	const addExclusion = useCallback(() => {
		if (!rule || !draftExclusion.trim()) return;
		const glob = draftExclusion.trim();
		if (rule.exclude_path_globs.includes(glob)) return;
		onExclusionsChange(rule.rule_id, [...rule.exclude_path_globs, glob]);
		setDraftExclusion("");
	}, [rule, draftExclusion, onExclusionsChange]);

	const removeExclusion = useCallback((glob: string) => {
		if (!rule) return;
		onExclusionsChange(rule.rule_id, rule.exclude_path_globs.filter((g) => g !== glob));
	}, [rule, onExclusionsChange]);

	const toggleEvent = useCallback((eventName: string) => {
		if (!rule) return;
		const events = new Set(rule.hookEvents);
		if (events.has(eventName)) {
			events.delete(eventName);
		} else {
			events.add(eventName);
		}
		onSetHookSurface(rule.rule_id, { events: [...events].sort() });
	}, [rule, onSetHookSurface]);

	const effectiveBehaviorSummary = useMemo(() => getEffectiveBehavior(rule), [rule]);

	return {
		draftExclusion,
		setDraftExclusion,
		sevColor,
		addExclusion,
		removeExclusion,
		toggleEvent,
		effectiveBehaviorSummary,
	};
}

export function RuleInspector({
	rule,
	onSetHookSurface,
	onSetRuleCliSurface,
	onExclusionsChange,
	onClose,
	isMobile,
}: RuleInspectorProps) {
	const {
		draftExclusion,
		setDraftExclusion,
		sevColor,
		addExclusion,
		removeExclusion,
		toggleEvent,
		effectiveBehaviorSummary,
	} = useRuleInspectorState(rule, onSetHookSurface, onExclusionsChange);

	if (!rule) return null;

	const content = (
		<div className="space-y-5 text-[0.875rem] font-sans">
			<RuleIdentitySection
				severity={rule.severity}
				source={rule.source}
				title={rule.title}
				description={rule.description}
				sevColor={sevColor}
			/>
			<PlacementSection
				ruleId={rule.rule_id}
				hookSupported={rule.hookSupported}
				hookEnabled={rule.hookEnabled}
				hookUnsupportedReason={rule.hookUnsupportedReason}
				onSetHookSurface={onSetHookSurface}
				cliSupported={rule.cliSupported}
				cliEnabled={rule.cliEnabled}
				cliRuleIds={rule.cliRuleIds}
				cliUnsupportedReason={rule.cliUnsupportedReason}
				onSetRuleCliSurface={onSetRuleCliSurface}
			/>
			{rule.hookSupported && (
				<HookParamsSection
					ruleId={rule.rule_id}
					hookAction={rule.hookAction}
					hookEvents={rule.hookEvents}
					onSetHookSurface={onSetHookSurface}
					onToggleEvent={toggleEvent}
				/>
			)}
			<PathExclusionsSection
				ruleId={rule.rule_id}
				source={rule.source}
				excludePathGlobs={rule.exclude_path_globs}
				draftExclusion={draftExclusion}
				onDraftChange={setDraftExclusion}
				onAdd={addExclusion}
				onRemove={removeExclusion}
			/>
			<InspectorFooter
				cliCounterparts={rule.cliCounterparts}
				hookCounterparts={rule.hookCounterparts}
				effectiveBehaviorSummary={effectiveBehaviorSummary}
			/>
		</div>
	);

	if (isMobile) {
		return (
			<Sheet open={!!rule} onOpenChange={(open) => !open && onClose()}>
				<SheetContent side="right" className="w-full sm:max-w-md overflow-y-auto bg-background p-6">
					<SheetHeader className="text-left mb-4">
						<SheetTitle className="font-mono text-foreground font-bold truncate max-w-[280px]" style={{ color: sevColor }}>
							{rule.rule_id}
						</SheetTitle>
						<SheetDescription className="text-muted-foreground font-sans">
							Operator configuration workspace
						</SheetDescription>
					</SheetHeader>
					{content}
				</SheetContent>
			</Sheet>
		);
	}

	return (
		<div className="w-96 shrink-0 border border-border bg-card/15 rounded-md p-4 space-y-4 overflow-y-auto text-[0.875rem] max-h-[80vh] transition-all animate-in fade-in slide-in-from-right-4 duration-300 ease-out-expo">
			<div className="flex items-center justify-between border-b border-border pb-2">
				<span className="font-mono font-bold text-foreground truncate max-w-[240px]" style={{ color: sevColor }}>
					{rule.rule_id}
				</span>
				<Button
					type="button"
					variant="ghost"
					size="icon"
					onClick={onClose}
					className="text-muted-foreground hover:text-foreground h-7 w-7 rounded transition-colors"
					aria-label="Close rule inspector"
				>
					<X className="w-4 h-4" />
				</Button>
			</div>
			{content}
		</div>
	);
}

export default RuleInspector;

