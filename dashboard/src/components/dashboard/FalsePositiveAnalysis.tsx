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
		runtimeErrorsCount,
		variableDecisionsCount,
		highConfidenceCount,
		mediumConfidenceCount,
		lowConfidenceCount,
	} = useMemo(() => {
		return {
			needsReviewCount: signals.filter(
				(s) => s.isAdvisorySuspect || s.isRuntimeErrorSuspect || s.isVariableSuspect,
			).length,
			runtimeErrorsCount: signals.filter((s) => s.isRuntimeErrorSuspect).length,
			variableDecisionsCount: signals.filter((s) => s.isVariableSuspect).length,
			highConfidenceCount: signals.filter((s) => s.confidence === "high").length,
			mediumConfidenceCount: signals.filter((s) => s.confidence === "medium").length,
			lowConfidenceCount: signals.filter((s) => s.confidence === "low").length,
		};
	}, [signals]);

	const selectedSignal = useMemo(() => {
		return signals.find((s) => s.rule_id === selectedRuleId) || null;
	}, [signals, selectedRuleId]);

	const top5Rules = useMemo(() => {
		return activeSignals.slice(0, 5).map((s) => ({
			rule_id: s.rule_id,
			score:
				tab === "advisory"
					? s.advisoryPressure
					: tab === "error"
						? s.runtimeErrorPressure
						: s.decisionVariance,
		}));
	}, [activeSignals, tab]);

	const maxBarScore = Math.max(...top5Rules.map((row) => row.score), 1);

	return (
		<div className="space-y-4">
			<div className="flex items-center justify-between">
				<h3 className="text-xs text-muted-foreground uppercase tracking-wider px-1 flex items-center gap-2">
					<Eye className="w-3.5 h-3.5" />
					Rule Calibration Triage
				</h3>
				<div className="flex gap-1" role="tablist" aria-label="Calibration Modes">
					{[
						{
							key: "advisory" as CalibrationMode,
							label: "Advisory pressure",
							icon: ShieldX,
							description: "Review rules that warning/context trigger often but allow sessions",
						},
						{
							key: "error" as CalibrationMode,
							label: "Runtime error pressure",
							icon: ShieldCheck,
							description: "Review rules causing exact or structured runtime errors",
						},
						{
							key: "variance" as CalibrationMode,
							label: "Decision variance",
							icon: AlertTriangle,
							description: "Review rules with highly inconsistent allow/block choices",
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
								"px-2 py-0.5 text-[10px] rounded-sm transition-colors uppercase flex items-center gap-1",
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
			<div className="grid grid-cols-4 gap-3">
				<SummaryCard
					icon={ShieldX}
					label="Needs Review"
					value={needsReviewCount}
					color="text-signal-ask"
				/>
				<SummaryCard
					icon={ShieldCheck}
					label="Runtime Errors"
					value={runtimeErrorsCount}
					color="text-signal-block"
				/>
				<SummaryCard
					icon={AlertTriangle}
					label="Variable Decisions"
					value={variableDecisionsCount}
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
			<div className="grid grid-cols-5 gap-3">
				{/* Left side: Triage queue summary and confidence distribution */}
				<div className="col-span-3 min-h-[260px] border border-border rounded-md bg-card/30 p-3 flex flex-col justify-between">
					<div className="space-y-2">
						<div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
							<Info className="w-3.5 h-3.5 text-primary" />
							Triage Queue Overview
						</div>
						<p className="text-[10px] text-muted-foreground leading-normal">
							Review rules flagged by the calibration engine. Set your triage lens to spot high advisory pressure, runtime error pressure, or decision variance. Click any row in the queue table below to inspect its supporting evidence in detail.
						</p>

						{/* Confidence Distribution */}
						<div className="pt-2 border-t border-border/30">
							<div className="text-[10px] text-muted-foreground uppercase font-semibold">
								Evidence Confidence Distribution
							</div>
							<div className="flex gap-4 mt-1">
								<div className="flex items-center gap-1.5 text-[10px]">
									<span className="w-1.5 h-1.5 rounded-full bg-signal-block" />
									<span className="text-muted-foreground">High:</span>
									<span className="font-mono text-foreground font-semibold">
										{highConfidenceCount}
									</span>
								</div>
								<div className="flex items-center gap-1.5 text-[10px]">
									<span className="w-1.5 h-1.5 rounded-full bg-signal-ask" />
									<span className="text-muted-foreground">Medium:</span>
									<span className="font-mono text-foreground font-semibold">
										{mediumConfidenceCount}
									</span>
								</div>
								<div className="flex items-center gap-1.5 text-[10px]">
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
						<div className="text-[10px] text-muted-foreground uppercase font-semibold mb-1.5">
							Top Rules under {tab === "advisory" ? "Advisory" : tab === "error" ? "Error" : "Variance"} Lens
						</div>
						{top5Rules.length > 0 ? (
							<div className="space-y-1.5">
								{top5Rules.map((row) => (
									<div
										key={row.rule_id}
										className="grid grid-cols-[120px_minmax(0,1fr)_30px] items-center gap-2 text-[9px]"
									>
										<span className="truncate font-mono text-muted-foreground" title={row.rule_id}>
											{row.rule_id}
										</span>
										<div className="h-2 rounded-sm bg-muted/40">
											<div
												className={cn(
													"h-full rounded-sm",
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
							<div className="text-[10px] text-muted-foreground italic">
								No suspect rules found for the active lens.
							</div>
						)}
					</div>
				</div>

				{/* Right side: Selected rule evidence panel */}
				<div className="col-span-2 min-h-[260px]">
					{selectedSignal ? (
						<div className="flex flex-col h-full bg-card border border-border rounded-md p-3 text-xs space-y-2">
							<div className="flex justify-between items-start border-b border-border pb-2">
								<div className="min-w-0 flex-1 pr-2">
									<div className="font-mono font-bold text-foreground truncate" title={selectedSignal.rule_id}>
										{selectedSignal.rule_id}
									</div>
									<div className="text-[10px] text-muted-foreground line-clamp-2 mt-0.5" title={getRuleDescription(selectedSignal.rule_id) || undefined}>
										{getRuleDescription(selectedSignal.rule_id) || "No description available"}
									</div>
								</div>
								<span className={cn(
									"text-[9px] px-1.5 py-0.5 rounded-sm shrink-0",
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
								<div className="text-center p-1 bg-muted/20 rounded">
									<div className="text-[9px] text-muted-foreground uppercase">Advisory</div>
									<div className="font-mono text-sm font-bold text-signal-ask">
										{selectedSignal.advisoryPressure}
									</div>
								</div>
								<div className="text-center p-1 bg-muted/20 rounded">
									<div className="text-[9px] text-muted-foreground uppercase">Errors</div>
									<div className="font-mono text-sm font-bold text-signal-block">
										{selectedSignal.runtimeErrorPressure}
									</div>
								</div>
								<div className="text-center p-1 bg-muted/20 rounded">
									<div className="text-[9px] text-muted-foreground uppercase">Variance</div>
									<div className="font-mono text-sm font-bold text-signal-error">
										{selectedSignal.decisionVariance}
									</div>
								</div>
							</div>

							<div className="space-y-1.5 flex-1 min-h-0 overflow-y-auto pr-1">
								<div className="text-[9px] text-muted-foreground uppercase tracking-wider font-semibold">
									Evidence Details
								</div>
								<div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[10px] text-muted-foreground">
									<div>Findings Count:</div>
									<div className="font-mono text-right text-foreground">{selectedSignal.totalFindings}</div>
									<div>Unique Sessions:</div>
									<div className="font-mono text-right text-foreground">{selectedSignal.sessionsCount}</div>
									<div>Allow After Advisory:</div>
									<div className="font-mono text-right text-foreground">{selectedSignal.allowAfterWarn}</div>
									<div>Errors Linked:</div>
									<div className="font-mono text-right text-foreground">{selectedSignal.errorCount}</div>
								</div>

								<div className="border-t border-border/30 pt-1.5 mt-1">
									<div className="text-[9px] text-muted-foreground uppercase tracking-wider font-semibold">
										Decision Mix
									</div>
									<div className="flex gap-1.5 items-center mt-1 text-[9px]">
										<span className="text-signal-block font-mono">Blocks: {selectedSignal.blockCount}</span>
										<span className="text-signal-ask font-mono">Warns: {selectedSignal.warnCount}</span>
										<span className="text-muted-foreground font-mono">Allows: {selectedSignal.allowCount}</span>
									</div>
								</div>

								{selectedSignal.recentExampleMessage && (
									<div className="border-t border-border/30 pt-1.5 mt-1">
										<div className="text-[9px] text-muted-foreground uppercase tracking-wider font-semibold">
											Recent Finding Message
										</div>
										<div className="bg-muted/30 border border-border/50 rounded p-1.5 mt-1 font-mono text-[9px] break-all leading-normal text-muted-foreground max-h-16 overflow-y-auto">
											{selectedSignal.recentExampleMessage}
										</div>
									</div>
								)}

								{selectedSignal.recentExampleError && (
									<div className="border-t border-border/30 pt-1.5 mt-1">
										<div className="text-[9px] text-muted-foreground uppercase tracking-wider font-semibold">
											Recent Error Message
										</div>
										<div className="bg-muted/30 border border-border/50 rounded p-1.5 mt-1 font-mono text-[9px] break-all leading-normal text-muted-foreground max-h-16 overflow-y-auto">
											{selectedSignal.recentExampleError}
										</div>
									</div>
								)}
							</div>
						</div>
					) : (
						<div className="flex flex-col items-center justify-center h-full bg-card border border-border border-dashed rounded-md p-4 text-center text-muted-foreground text-[10px]">
							<Eye className="w-5 h-5 mb-1 text-muted-foreground/60 animate-pulse" />
							Select a rule from the triage queue to inspect evidence
						</div>
					)}
				</div>
			</div>

			{/* Primary Table */}
			<div className="border border-border rounded-md bg-card/30 overflow-hidden">
				<table className="w-full text-xs">
					<thead>
						<tr className="border-b border-border text-muted-foreground text-[10px] uppercase">
							<th className="text-left px-3 py-2">Rule</th>
							<th className="text-left px-3 py-2">Reason</th>
							<th className="text-left px-3 py-2">Evidence</th>
							<th className="text-left px-3 py-2">Decision Mix</th>
							<th className="text-right px-3 py-2">Sessions</th>
							<th className="text-right px-3 py-2">Score</th>
							<th className="text-left px-3 py-2">Confidence</th>
							<th className="px-3 py-2 w-8" />
							<th className="px-3 py-2 text-right">
								{activeSignals.length > TABLE_DEFAULT_LIMIT && (
									<button
										type="button"
										onClick={() => setShowAll((v) => !v)}
										className="text-[10px] text-primary hover:underline whitespace-nowrap"
									>
										{showAll ? "Show less" : `Show all ${activeSignals.length}`}
									</button>
								)}
							</th>
						</tr>
					</thead>
					<tbody>
						{active.length === 0 ? (
							<tr>
								<td colSpan={9} className="text-center py-8 text-muted-foreground text-xs italic">
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

							const label = `Rule ${s.rule_id} (${tab === "advisory" ? "Advisory pressure" : tab === "error" ? "Runtime error pressure" : "Decision variance"} suspect, score ${currentScore})`;

							return (
								<tr
									key={s.rule_id}
									onClick={() => setSelectedRuleId(s.rule_id)}
									className={cn(
										"border-b border-border/50 hover:bg-muted/20 transition-colors cursor-pointer",
										selectedRuleId === s.rule_id && "bg-muted/30 border-l-2 border-l-primary"
									)}
								>
									<td
										className="px-3 py-1.5 font-medium"
										title={getRuleDescription(s.rule_id) || s.rule_id}
									>
										<div className="font-mono">{s.rule_id}</div>
										{getRuleDescription(s.rule_id) && (
											<div className="text-[10px] text-muted-foreground font-normal leading-tight mt-0.5">
												{getRuleDescription(s.rule_id)}
											</div>
										)}
									</td>
									<td className="px-3 py-1.5">
										<div className="flex flex-wrap gap-1">
											{s.isAdvisorySuspect && (
												<span className="text-[9px] px-1 py-0.5 rounded-sm bg-signal-ask/20 text-signal-ask font-semibold">
													Advisory
												</span>
											)}
											{s.isRuntimeErrorSuspect && (
												<span className="text-[9px] px-1 py-0.5 rounded-sm bg-signal-block/20 text-signal-block font-semibold">
													Runtime Error
												</span>
											)}
											{s.isVariableSuspect && (
												<span className="text-[9px] px-1 py-0.5 rounded-sm bg-signal-error/20 text-signal-error font-semibold">
													Variable
												</span>
											)}
											{s.isClean && (
												<span className="text-[9px] px-1 py-0.5 rounded-sm bg-muted text-muted-foreground font-semibold">
													Clean
												</span>
											)}
										</div>
									</td>
									<td className="px-3 py-1.5 text-muted-foreground font-mono text-[10px]">
										{s.totalFindings > 0 ? (
											<span>{s.totalFindings} findings</span>
										) : s.errorCount > 0 ? (
											<span>{s.errorCount} errors</span>
										) : (
											<span>0 findings</span>
										)}
									</td>
									<td className="px-3 py-1.5">
										<div className="flex gap-1 text-[10px] font-mono">
											<span className="text-signal-block" title="Blocks">B:{s.blockCount}</span>
											<span className="text-signal-ask" title="Warns">W:{s.warnCount}</span>
											<span className="text-muted-foreground" title="Allows">A:{s.allowCount}</span>
										</div>
									</td>
									<td className="px-3 py-1.5 text-right font-mono">{s.sessionsCount}</td>
									<td className="px-3 py-1.5 text-right font-semibold">
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
									<td className="px-3 py-1.5">
										<span
											className={cn(
												"text-[9px] px-1.5 py-0.5 rounded-sm uppercase font-semibold",
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
										className="px-3 py-1.5"
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
									<td />
								</tr>
							);
						}))}
					</tbody>
				</table>
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
		<div className="flex items-center gap-2.5 px-3 py-2.5 rounded-md border border-border bg-card">
			<Icon className={cn("w-4 h-4 shrink-0", color)} />
			<div>
				<div className={cn("text-lg font-semibold leading-tight", color)}>
					{value}
				</div>
				<div className="text-[10px] text-muted-foreground uppercase tracking-wider">
					{label}
				</div>
			</div>
		</div>
	);
});
