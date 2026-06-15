import { AlertTriangle, Eye, Flag, ShieldCheck, ShieldX, Info } from "lucide-react";
import type { ElementType } from "react";
import { memo, useEffect, useMemo, useState } from "react";
import { getRuleDescription } from "@/lib/ruleDescriptions";
import { cn } from "@/lib/utils";
import type { HookResult, RuleFinding } from "@/types/slopgate";
import { FlagButton } from "./FlagButton";
import { computeCalibrationSignals } from "@/lib/ruleCalibration";
import type { CalibrationMode } from "@/lib/ruleCalibration";

interface Props {
	rules: RuleFinding[];
	results: HookResult[];
}

const TABLE_DEFAULT_LIMIT = 10;

function lensLabel(tab: CalibrationMode): string {
	if (tab === "advisory") return "Advisory pressure";
	if (tab === "error") return "Runtime/repeat score";
	return "Persistence score";
}

function lensName(tab: CalibrationMode): string {
	if (tab === "advisory") return "Advisory";
	if (tab === "error") return "Runtime/repeat";
	return "Persistence";
}

export function FalsePositiveAnalysis({ rules, results }: Props) {
	const [tab, setTab] = useState<CalibrationMode>("advisory");
	const [showAll, setShowAll] = useState(false);
	const [selectedRuleId, setSelectedRuleId] = useState<string | null>(null);

	// Reset showAll when tab changes
	useEffect(() => {
		if (tab) {
			setShowAll(false);
		}
	}, [tab]);

	const signals = useMemo(
		() => computeCalibrationSignals(rules, results),
		[rules, results],
	);

	const activeSignals = useMemo(() => {
		const sorted = [...signals];
		if (tab === "advisory") {
			sorted.sort((a, b) => b.advisoryPressure - a.advisoryPressure);
		} else if (tab === "error") {
			sorted.sort((a, b) => b.runtimeErrorPressure - a.runtimeErrorPressure);
		} else {
			sorted.sort((a, b) => b.decisionVariance - a.decisionVariance);
		}
		return sorted;
	}, [signals, tab]);

	const active = useMemo(() => {
		return showAll ? activeSignals : activeSignals.slice(0, TABLE_DEFAULT_LIMIT);
	}, [activeSignals, showAll]);

	// Auto-select first rule when active list changes or when selectedRuleId becomes invalid
	useEffect(() => {
		if (activeSignals.length > 0) {
			const exists = activeSignals.some((s) => s.rule_id === selectedRuleId);
			if (!exists) {
				setSelectedRuleId(activeSignals[0].rule_id);
			}
		} else {
			setSelectedRuleId(null);
		}
	}, [activeSignals, selectedRuleId]);

	const {
		needsReviewCount,
		repeatFireRulesCount,
		persistentRulesCount,
		highConfidenceCount,
		mediumConfidenceCount,
		lowConfidenceCount,
	} = useMemo(() => {
		return {
			needsReviewCount: signals.filter(
				(s) => s.isAdvisorySuspect || s.isRuntimeErrorSuspect || s.isVariableSuspect,
			).length,
			repeatFireRulesCount: signals.filter((s) => s.isRuntimeErrorSuspect).length,
			persistentRulesCount: signals.filter((s) => s.isVariableSuspect).length,
			highConfidenceCount: signals.filter((s) => s.confidence === "high").length,
			mediumConfidenceCount: signals.filter((s) => s.confidence === "medium").length,
			lowConfidenceCount: signals.filter((s) => s.confidence === "low").length,
		};
	}, [signals]);

	const selectedSignal = useMemo(() => {
		return signals.find((s) => s.rule_id === selectedRuleId) || null;
	}, [signals, selectedRuleId]);

	const top5Rules = useMemo(() => {
		return activeSignals
			.map((s) => ({
				rule_id: s.rule_id,
				score:
					tab === "advisory"
						? s.advisoryPressure
						: tab === "error"
							? s.runtimeErrorPressure
							: s.decisionVariance,
			}))
			.filter((row) => row.score > 0)
			.slice(0, 5);
	}, [activeSignals, tab]);

	const maxBarScore = Math.max(...top5Rules.map((row) => row.score), 1);

	return (
		<div className="space-y-4">
			<div className="flex items-center justify-between">
				<h3 className="text-sm font-semibold text-foreground px-1 flex items-center gap-2">
					<Eye className="w-4 h-4 text-primary" />
					Rule Calibration Triage
				</h3>
				<div className="flex gap-1" role="tablist" aria-label="Calibration Modes">
					{[
						{
							key: "advisory" as CalibrationMode,
							label: "Advisory pressure",
							icon: ShieldX,
							description: "Review rules that warn often but are usually allowed",
						},
						{
							key: "error" as CalibrationMode,
							label: "Runtime/repeat score",
							icon: ShieldCheck,
							description: "Rank raw detectors by repeated firing, runtime errors, finding volume, and session breadth",
						},
						{
							key: "variance" as CalibrationMode,
							label: "Persistence score",
							icon: AlertTriangle,
							description: "Rank delivered findings by persistence, finding volume, and session breadth",
						},
					].map(({ key, label, icon: Icon, description }) => (
						<button
							type="button"
							key={key}
							role="tab"
							aria-selected={tab === key}
							aria-label={`${label}: ${description}`}
							title={description}
							onClick={() => setTab(key)}
							className={cn(
								"px-2.5 py-1 text-xs rounded-md transition-colors font-medium flex items-center gap-1.5",
								tab === key
									? "bg-primary text-primary-foreground"
									: "text-muted-foreground hover:bg-muted",
							)}
						>
							<Icon className="w-3 h-3" />
							{label}
						</button>
					))}
				</div>
			</div>

			{/* Horizontal Diagnostic Strip */}
			<div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
				<SummaryCard
					icon={ShieldX}
					label="Needs Review"
					value={needsReviewCount}
					color="text-signal-ask"
				/>
				<SummaryCard
					icon={ShieldCheck}
					label="Runtime/Repeat Rules"
					value={repeatFireRulesCount}
					color="text-signal-block"
				/>
				<SummaryCard
					icon={AlertTriangle}
					label="Persistent Rules"
					value={persistentRulesCount}
					color="text-signal-error"
				/>
				<SummaryCard
					icon={Flag}
					label="Rules Analyzed"
					value={signals.length}
					color="text-foreground"
				/>
			</div>

			{/* Operator Summary & Selected Evidence Panel */}
			<div className="grid grid-cols-1 lg:grid-cols-5 gap-3">
				{/* Left side: Triage queue summary and confidence distribution */}
				<div className="col-span-1 lg:col-span-3 min-h-[260px] border border-border rounded-md bg-card/30 p-3 flex flex-col justify-between">
					<div className="space-y-2">
						<div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
							<Info className="w-3.5 h-3.5 text-primary" />
							Triage Queue Overview
						</div>
						<p className="text-xs text-muted-foreground leading-normal font-sans">
							Tune policy enforcement by reviewing flagged rules. Select a lens to rank warning mismatches, repeated raw detector firings, or delivered findings that persisted across comparable hook runs, then click any row to inspect session evidence.
						</p>

						{/* Confidence Distribution */}
						<div className="pt-2 border-t border-border/30">
							<div className="text-xs font-semibold text-foreground">
								Evidence Confidence Distribution
							</div>
							<div className="flex gap-4 mt-1">
								<div className="flex items-center gap-1.5 text-xs">
									<span className="w-1.5 h-1.5 rounded-full bg-signal-block" />
									<span className="text-muted-foreground">High:</span>
									<span className="font-mono text-foreground font-semibold">
										{highConfidenceCount}
									</span>
								</div>
								<div className="flex items-center gap-1.5 text-xs">
									<span className="w-1.5 h-1.5 rounded-full bg-signal-ask" />
									<span className="text-muted-foreground">Medium:</span>
									<span className="font-mono text-foreground font-semibold">
										{mediumConfidenceCount}
									</span>
								</div>
								<div className="flex items-center gap-1.5 text-xs">
									<span className="w-1.5 h-1.5 rounded-full bg-muted-foreground/50" />
									<span className="text-muted-foreground">Low:</span>
									<span className="font-mono text-foreground font-semibold">
										{lowConfidenceCount}
									</span>
								</div>
							</div>
						</div>
					</div>

					{/* Mini Bar Chart of Top Rules */}
					<div className="pt-3 border-t border-border/30 mt-2">
						<div className="text-xs font-semibold text-foreground mb-1.5">
							Top Rules under {lensName(tab)} Lens
						</div>
						{top5Rules.length > 0 ? (
							<div className="space-y-1.5">
								{top5Rules.map((row) => (
									<div
										key={row.rule_id}
										className="grid grid-cols-[120px_minmax(0,1fr)_30px] items-center gap-2 text-xs"
									>
										<span className="truncate font-mono text-muted-foreground/80" title={row.rule_id}>
											{row.rule_id}
										</span>
										<div className="h-2 rounded-sm bg-muted/40">
											<div
												className={cn(
													"h-full rounded-sm transition-all duration-300 ease-out-quart",
													tab === "advisory"
														? "bg-signal-ask"
														: tab === "error"
															? "bg-signal-block"
															: "bg-signal-error",
												)}
												style={{
													width: `${Math.max(
														1,
														(row.score / maxBarScore) * 100,
													)}%`,
												}}
											/>
										</div>
										<span className="text-right font-mono text-foreground font-bold">
											{row.score}
										</span>
									</div>
								))}
							</div>
						) : (
							<div className="text-xs text-muted-foreground italic">
								No suspect rules found for the active lens.
							</div>
						)}
					</div>
				</div>

				{/* Right side: Selected rule evidence panel */}
				<div className="col-span-1 lg:col-span-2 min-h-[260px]">
					{selectedSignal ? (
						<div key={selectedSignal.rule_id} className="flex flex-col h-full bg-card border border-border rounded-md p-3 text-xs space-y-2 animate-fade-in">
							<div className="flex justify-between items-start border-b border-border pb-2">
								<div className="min-w-0 flex-1 pr-2">
									<div className="font-mono font-bold text-foreground truncate" title={selectedSignal.rule_id}>
										{selectedSignal.rule_id}
									</div>
									<div className="text-xs text-muted-foreground line-clamp-2 mt-0.5" title={getRuleDescription(selectedSignal.rule_id) || undefined}>
										{getRuleDescription(selectedSignal.rule_id) || "No description available"}
									</div>
								</div>
								<span className={cn(
									"text-xs px-2.5 py-0.5 rounded-md font-semibold shrink-0",
									selectedSignal.severity === "CRITICAL"
										? "bg-signal-block/20 text-signal-block"
										: selectedSignal.severity === "HIGH"
											? "bg-severity-high/20 text-severity-high"
											: selectedSignal.severity === "MEDIUM"
												? "bg-signal-ask/20 text-signal-ask"
												: "bg-muted text-muted-foreground"
								)}>
									{selectedSignal.severity}
								</span>
							</div>

							<div className="grid grid-cols-3 gap-2 border-b border-border/50 pb-2">
								<div className="text-center p-1.5 bg-muted/20 rounded">
									<div className="text-xs font-semibold text-muted-foreground">Advisory</div>
									<div className="font-mono text-sm font-bold text-signal-ask">
										{selectedSignal.advisoryPressure}%
									</div>
								</div>
								<div className="text-center p-1.5 bg-muted/20 rounded">
									<div className="text-xs font-semibold text-muted-foreground">Runtime score</div>
									<div className="font-mono text-sm font-bold text-signal-block">
										{selectedSignal.runtimeErrorPressure}
									</div>
								</div>
								<div className="text-center p-1.5 bg-muted/20 rounded">
									<div className="text-xs font-semibold text-muted-foreground">Persist score</div>
									<div className="font-mono text-sm font-bold text-signal-error">
										{selectedSignal.decisionVariance}
									</div>
								</div>
							</div>

							<div className="space-y-1.5 flex-1 min-h-0 overflow-y-auto pr-1">
								<div className="text-xs font-semibold text-foreground">
									Evidence Details
								</div>
								<div className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs text-muted-foreground">
									<div>Raw Findings:</div>
									<div className="font-mono text-right text-foreground">{selectedSignal.totalFindings}</div>
									<div>Unique Sessions:</div>
									<div className="font-mono text-right text-foreground">{selectedSignal.sessionsCount}</div>
									<div>Allowed After Warning:</div>
									<div className="font-mono text-right text-foreground">{selectedSignal.allowAfterWarn}</div>
									<div>Repeat-fire Sessions:</div>
									<div className="font-mono text-right text-foreground">{selectedSignal.repeatFireSessions}</div>
									<div>Delivered Sessions:</div>
									<div className="font-mono text-right text-foreground">{selectedSignal.deliveredSessions}</div>
									<div>Later Comparable Findings:</div>
									<div className="font-mono text-right text-foreground">{selectedSignal.persistentDeliveredFindings}</div>
								</div>

								<div className="border-t border-border/30 pt-1.5 mt-1">
									<div className="text-xs font-semibold text-foreground">
										Decision Mix
									</div>
									<div className="flex gap-2.5 items-center mt-1 text-xs">
										<span className="text-signal-block font-mono">Blocked: {selectedSignal.blockCount}</span>
										<span className="text-signal-ask font-mono">Warned: {selectedSignal.warnCount}</span>
										<span className="text-muted-foreground font-mono">Allowed: {selectedSignal.allowCount}</span>
									</div>
								</div>

								{selectedSignal.recentExampleMessage && (
									<div className="border-t border-border/30 pt-1.5 mt-1">
										<div className="text-xs font-semibold text-foreground">
											Recent Finding Message
										</div>
										<div className="bg-muted/30 border border-border/50 rounded p-1.5 mt-1 font-mono text-xs break-all leading-normal text-muted-foreground max-h-16 overflow-y-auto">
											{selectedSignal.recentExampleMessage}
										</div>
									</div>
								)}

								{selectedSignal.recentExampleError && (
									<div className="border-t border-border/30 pt-1.5 mt-1">
										<div className="text-xs font-semibold text-foreground">
											Recent Error Message
										</div>
										<div className="bg-muted/30 border border-border/50 rounded p-1.5 mt-1 font-mono text-xs break-all leading-normal text-muted-foreground max-h-16 overflow-y-auto">
											{selectedSignal.recentExampleError}
										</div>
									</div>
								)}
							</div>
						</div>
					) : (
						<div className="flex flex-col items-center justify-center h-full bg-card border border-border border-dashed rounded-md p-4 text-center text-muted-foreground text-xs">
							<Eye className="w-5 h-5 mb-1 text-muted-foreground/60 animate-pulse" />
							Select a rule from the triage queue to inspect evidence
						</div>
					)}
				</div>
			</div>

			{/* Primary Table */}
			<div className="border border-border rounded-md bg-card/30 overflow-hidden">
				<div className="overflow-x-auto">
					<table className="w-full text-xs min-w-[800px]">
					<thead>
						<tr className="border-b border-border text-muted-foreground text-xs font-semibold">
							<th className="text-left px-3 py-2.5">Rule</th>
							<th className="text-left px-3 py-2.5">Reason</th>
							<th className="text-left px-3 py-2.5">Evidence</th>
							<th className="text-left px-3 py-2.5">Decision Mix</th>
							<th className="text-right px-3 py-2.5">Sessions</th>
							<th className="text-right px-3 py-2.5">Score</th>
							<th className="text-left px-3 py-2.5">Confidence</th>
							<th className="px-3 py-2.5 w-12 text-right">Actions</th>
						</tr>
					</thead>
					<tbody>
						{active.length === 0 ? (
							<tr>
								<td colSpan={8} className="text-center py-8 text-muted-foreground text-xs italic">
									Not enough evidence for calibration.
								</td>
							</tr>
						) : (
							active.map((s) => {
							const currentScore =
								tab === "advisory"
									? s.advisoryPressure
									: tab === "error"
										? s.runtimeErrorPressure
										: s.decisionVariance;

							const label = `Rule ${s.rule_id} (${lensLabel(tab)} suspect, score ${currentScore})`;

							return (
								<tr
									key={s.rule_id}
									onClick={() => setSelectedRuleId(s.rule_id)}
									className={cn(
										"border-b border-border/50 transition-all duration-200 ease-out-quart cursor-pointer hover:bg-muted/10",
										selectedRuleId === s.rule_id
											? "bg-primary/5 text-foreground font-medium"
											: "text-muted-foreground/90 hover:text-foreground"
									)}
								>
									<td
										className="px-3 py-2 font-medium"
										title={getRuleDescription(s.rule_id) || s.rule_id}
									>
										<button
											type="button"
											onClick={(event) => {
												event.stopPropagation();
												setSelectedRuleId(s.rule_id);
											}}
											aria-pressed={selectedRuleId === s.rule_id}
											className="flex items-center gap-2 font-mono text-foreground text-left focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring rounded-sm"
										>
											{selectedRuleId === s.rule_id && (
												<span className="w-1.5 h-1.5 rounded-full bg-primary shrink-0" />
											)}
											{s.rule_id}
										</button>
										{getRuleDescription(s.rule_id) && (
											<div className="text-xs text-muted-foreground font-normal leading-tight mt-0.5">
												{getRuleDescription(s.rule_id)}
											</div>
										)}
									</td>
									<td className="px-3 py-2">
										<div className="flex flex-wrap gap-1">
											{s.isAdvisorySuspect && (
												<span className="text-xs px-2 py-0.5 rounded-md bg-signal-ask/15 text-signal-ask font-semibold">
													Advisory
												</span>
											)}
								{s.isRuntimeErrorSuspect && (
									<span className="text-xs px-2 py-0.5 rounded-md bg-signal-block/15 text-signal-block font-semibold">
										Runtime/repeat
									</span>
											)}
											{s.isVariableSuspect && (
												<span className="text-xs px-2 py-0.5 rounded-md bg-signal-error/15 text-signal-error font-semibold">
													Persistent
												</span>
											)}
											{s.isClean && (
												<span className="text-xs px-2 py-0.5 rounded-md bg-muted text-muted-foreground font-semibold">
													Clean
												</span>
											)}
										</div>
									</td>
									<td className="px-3 py-2 text-muted-foreground font-mono text-xs">
										{s.totalFindings > 0 ? (
											<span>{s.totalFindings} findings</span>
										) : s.runtimeErrorCount > 0 ? (
											<span>{s.runtimeErrorCount} runtime errors</span>
										) : (
											<span>0 findings</span>
										)}
									</td>
									<td className="px-3 py-2">
										<div className="flex gap-2 text-xs font-mono">
											<span className="text-signal-block font-semibold" title="Blocked">B:{s.blockCount}</span>
											<span className="text-signal-ask font-semibold" title="Warned">W:{s.warnCount}</span>
											<span className="text-muted-foreground" title="Allowed">A:{s.allowCount}</span>
										</div>
									</td>
									<td className="px-3 py-2 text-right font-mono text-xs">{s.sessionsCount}</td>
									<td className="px-3 py-2 text-right font-semibold text-xs">
										<span
											className={cn(
												tab === "advisory" && s.isAdvisorySuspect
													? "text-signal-ask"
													: tab === "error" && s.isRuntimeErrorSuspect
														? "text-signal-block"
														: tab === "variance" && s.isVariableSuspect
															? "text-signal-error"
															: "text-foreground",
											)}
										>
											{currentScore}
										</span>
									</td>
									<td className="px-3 py-2">
										<span
											className={cn(
												"text-xs px-2 py-0.5 rounded-md font-semibold capitalize",
												s.confidence === "high"
													? "bg-signal-block/20 text-signal-block"
													: s.confidence === "medium"
														? "bg-signal-ask/20 text-signal-ask"
														: "bg-muted text-muted-foreground",
											)}
										>
											{s.confidence}
										</span>
									</td>
									<td
										className="px-3 py-2 text-right"
										onClick={(e) => e.stopPropagation()}
										onKeyDown={(e) => e.stopPropagation()}
									>
										<FlagButton
											itemType="rule"
											itemId={s.rule_id}
											label={label}
											compact
										/>
									</td>
								</tr>
							);
						}))}
					</tbody>
				</table>
			</div>
				{activeSignals.length > TABLE_DEFAULT_LIMIT && (
					<div className="flex justify-end p-2 border-t border-border/50 bg-card/10">
						<button
							type="button"
							onClick={() => setShowAll((v) => !v)}
							className="text-xs font-semibold text-primary hover:underline px-2 py-1"
						>
							{showAll ? "Show less" : `Show all ${activeSignals.length} rules`}
						</button>
					</div>
				)}
			</div>
		</div>
	);
}

const SummaryCard = memo(function SummaryCard({
	icon: Icon,
	label,
	value,
	color,
}: {
	icon: ElementType;
	label: string;
	value: number;
	color: string;
}) {
	return (
		<div className="flex items-center gap-3 px-3.5 py-3 rounded-lg border border-border bg-card/40 transition-colors hover:bg-card/60">
			<Icon className={cn("w-4 h-4 shrink-0 opacity-75", color)} />
			<div>
				<div className="text-xl font-bold font-sans tracking-tight text-foreground leading-none mb-0.5">
					{value}
				</div>
				<div className="text-[11px] font-medium text-muted-foreground leading-none">
					{label}
				</div>
			</div>
		</div>
	);
});
