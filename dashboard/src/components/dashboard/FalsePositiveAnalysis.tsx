import { AlertTriangle, Eye, Flag, ShieldCheck, ShieldX } from "lucide-react";
import { memo, useEffect, useMemo, useState } from "react";
import type { ElementType } from "react";
import { resolveDecision } from "@/hooks/useTraceData";
import { getRuleDescription } from "@/lib/ruleDescriptions";
import { cn } from "@/lib/utils";
import type {
	Decision,
	HookResult,
	RuleFinding,
	Severity,
} from "@/types/slopgate";
import { FlagButton } from "./FlagButton";

interface FPSignal {
	rule_id: string;
	fpScore: number;
	fnScore: number;
	totalFindings: number;
	blockCount: number;
	warnCount: number;
	allowAfterWarn: number;
	errorOverride: number;
	severity: Severity;
	inconsistencyRate: number;
}

interface Props {
	rules: RuleFinding[];
	results: HookResult[];
}

type TabView = "fp" | "fn" | "inconsistent";

function computeFPFNSignals(
	rules: RuleFinding[],
	results: HookResult[],
): FPSignal[] {
	const byRule = new Map<string, RuleFinding[]>();
	for (const r of rules) {
		if (!byRule.has(r.rule_id)) byRule.set(r.rule_id, []);
		byRule.get(r.rule_id)?.push(r);
	}

	const sessionFinalDecision = new Map<string, Decision>();
	for (const r of results) {
		const d = resolveDecision(r.findings);
		const existing = sessionFinalDecision.get(r.session_id);
		if (!existing || d === "block" || d === "deny") {
			sessionFinalDecision.set(r.session_id, d);
		}
	}

	const errorsByRule = new Map<string, number>();
	for (const r of results) {
		for (const err of r.errors ?? []) {
			for (const [ruleId] of byRule) {
				if (err.includes(ruleId)) {
					errorsByRule.set(ruleId, (errorsByRule.get(ruleId) || 0) + 1);
				}
			}
		}
	}

	const signals: FPSignal[] = [];

	for (const [rule_id, findings] of byRule) {
		const totalFindings = findings.length;
		if (totalFindings < 2) continue;

		const decisions = findings.map((f) => f.decision ?? "context");
		const blockCount = decisions.filter(
			(d) => d === "block" || d === "deny",
		).length;
		const warnCount = decisions.filter(
			(d) => d === "warn" || d === "context",
		).length;
		const allowCount = decisions.filter((d) => d === "allow").length;

		const sessionsWithRule = [...new Set(findings.map((f) => f.session_id))];
		const allowAfterWarn = sessionsWithRule.filter((sid) => {
			const ruleDecisions = findings
				.filter((f) => f.session_id === sid)
				.map((f) => f.decision ?? "context");
			const hadWarning = ruleDecisions.some(
				(d) => d === "warn" || d === "ask" || d === "context",
			);
			const sessionAllowed = sessionFinalDecision.get(sid) === "allow";
			return hadWarning && sessionAllowed;
		}).length;

		const uniqueDecisions = new Set(decisions);
		const inconsistencyRate = uniqueDecisions.size / Math.min(totalFindings, 6);

		const fpScore =
			(allowAfterWarn / Math.max(sessionsWithRule.length, 1)) * 50 +
			(warnCount / totalFindings) * 20 +
			inconsistencyRate * 30;

		const errorOverride = errorsByRule.get(rule_id) || 0;
		const severity = findings[0].severity;
		const severityWeight =
			severity === "CRITICAL"
				? 4
				: severity === "HIGH"
					? 3
					: severity === "MEDIUM"
						? 2
						: 1;
		const fnScore =
			(errorOverride / Math.max(totalFindings, 1)) * 40 +
			(allowCount / totalFindings) * severityWeight * 15;

		signals.push({
			rule_id,
			fpScore,
			fnScore,
			totalFindings,
			blockCount,
			warnCount,
			allowAfterWarn,
			errorOverride,
			severity,
			inconsistencyRate,
		});
	}

	return signals.sort((a, b) => b.fpScore - a.fpScore);
}

const TABLE_DEFAULT_LIMIT = 10;
const BAR_MAX_WIDTH_PERCENT = 100;

export function FalsePositiveAnalysis({ rules, results }: Props) {
	const [tab, setTab] = useState<TabView>("fp");
	const [showAll, setShowAll] = useState(false);

	// Reset showAll when tab changes
	useEffect(() => setShowAll(false), []);

	const signals = useMemo(
		() => computeFPFNSignals(rules, results),
		[rules, results],
	);

	const { active, allActive, barData, highFPCount, highFNCount, noisyCount } =
		useMemo(() => {
			const fpSorted = [...signals].sort((a, b) => b.fpScore - a.fpScore);
			const fnSorted = [...signals].sort((a, b) => b.fnScore - a.fnScore);
			const inconsistentSorted = [...signals].sort(
				(a, b) => b.inconsistencyRate - a.inconsistencyRate,
			);

			const allActive =
				tab === "fp" ? fpSorted : tab === "fn" ? fnSorted : inconsistentSorted;
			const active = showAll
				? allActive
				: allActive.slice(0, TABLE_DEFAULT_LIMIT);
			const barData = active.map((s) => ({
				rule: s.rule_id.length > 22 ? `${s.rule_id.slice(0, 20)}…` : s.rule_id,
				fullRule: s.rule_id,
				score: Math.round(
					tab === "fp"
						? s.fpScore
						: tab === "fn"
							? s.fnScore
							: s.inconsistencyRate * 100,
				),
				findings: s.totalFindings,
				blocks: s.blockCount,
				warns: s.warnCount,
			}));

			return {
				active,
				allActive,
				barData,
				highFPCount: signals.filter((s) => s.fpScore > 40).length,
				highFNCount: signals.filter((s) => s.fnScore > 30).length,
				noisyCount: signals.filter((s) => s.inconsistencyRate > 0.5).length,
			};
		}, [signals, tab, showAll]);

	const summaryPie = useMemo(
		() => [
			{ id: "Likely FP", value: highFPCount, color: "hsl(38, 92%, 50%)" },
			{ id: "Likely FN", value: highFNCount, color: "hsl(0, 85%, 60%)" },
			{ id: "Noisy", value: noisyCount, color: "hsl(300, 70%, 55%)" },
			{
				id: "Clean",
				value: Math.max(
					0,
					signals.length - highFPCount - highFNCount - noisyCount,
				),
				color: "hsl(142, 50%, 45%)",
			},
		],
		[highFPCount, highFNCount, noisyCount, signals.length],
	);
	const maxBarScore = Math.max(...barData.map((row) => row.score), 1);
	const summaryTotal = Math.max(
		summaryPie.reduce((sum, item) => sum + item.value, 0),
		1,
	);
	const summaryStops = summaryPie.reduce(
		(acc, item) => {
			const start = acc.cursor;
			const end = start + (item.value / summaryTotal) * 100;
			return {
				cursor: end,
				stops: [
					...acc.stops,
					`${item.color} ${start.toFixed(2)}% ${end.toFixed(2)}%`,
				],
			};
		},
		{ cursor: 0, stops: [] as string[] },
	);

	return (
		<div className="space-y-4">
			<div className="flex items-center justify-between">
				<h3 className="text-xs text-muted-foreground uppercase tracking-wider px-1 flex items-center gap-2">
					<Eye className="w-3.5 h-3.5" />
					False Positive / Negative Analysis
				</h3>
				<div className="flex gap-1">
					{[
						{ key: "fp" as TabView, label: "FP suspects", icon: ShieldX },
						{ key: "fn" as TabView, label: "FN suspects", icon: ShieldCheck },
						{
							key: "inconsistent" as TabView,
							label: "Noisy",
							icon: AlertTriangle,
						},
					].map(({ key, label, icon: Icon }) => (
						<button
							type="button"
							key={key}
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

			<div className="grid grid-cols-4 gap-3">
				<SummaryCard
					icon={ShieldX}
					label="FP Suspects"
					value={highFPCount}
					color="text-signal-ask"
				/>
				<SummaryCard
					icon={ShieldCheck}
					label="FN Suspects"
					value={highFNCount}
					color="text-signal-block"
				/>
				<SummaryCard
					icon={AlertTriangle}
					label="Noisy Rules"
					value={noisyCount}
					color="text-signal-error"
				/>
				<SummaryCard
					icon={Flag}
					label="Rules Analyzed"
					value={signals.length}
					color="text-foreground"
				/>
			</div>

			<div className="grid grid-cols-5 gap-3">
				<div className="col-span-3 h-[260px] border border-border rounded-md bg-card/30 p-2">
					{barData.length > 0 ? (
						<div className="flex h-full flex-col justify-center gap-2">
							{barData.map((row) => (
								<div
									key={row.fullRule}
									className="grid grid-cols-[150px_minmax(0,1fr)_38px] items-center gap-2 text-[10px]"
									title={`${row.fullRule}: score ${row.score}, findings ${row.findings}, blocks ${row.blocks}, warns ${row.warns}`}
								>
									<span className="truncate font-mono text-muted-foreground">
										{row.rule}
									</span>
									<div className="h-3 rounded-sm bg-muted/40">
										<div
											className={cn(
												"h-full rounded-sm",
												tab === "fp"
													? "bg-signal-ask"
													: tab === "fn"
														? "bg-signal-block"
														: "bg-signal-error",
											)}
											style={{
												width: `${Math.max(
													1,
													(row.score / maxBarScore) * BAR_MAX_WIDTH_PERCENT,
												)}%`,
											}}
										/>
									</div>
									<span className="text-right font-mono text-foreground">
										{row.score}
									</span>
								</div>
							))}
						</div>
					) : (
						<div className="flex items-center justify-center h-full text-muted-foreground text-xs">
							Not enough data for analysis
						</div>
					)}
				</div>

				<div className="col-span-2 h-[260px] border border-border rounded-md bg-card/30 p-2">
					<h4 className="text-[10px] text-muted-foreground uppercase mb-1 text-center">
						Rule Health
					</h4>
					<div className="grid h-[calc(100%-1rem)] grid-cols-[minmax(0,1fr)_88px] items-center gap-3">
						<div className="grid place-items-center">
							<div
								className="grid h-32 w-32 place-items-center rounded-full"
								style={{
									background: `conic-gradient(${summaryStops.stops.join(", ")})`,
								}}
								title={summaryPie
									.map((item) => `${item.id}: ${item.value}`)
									.join(", ")}
							>
								<div className="grid h-16 w-16 place-items-center rounded-full bg-card text-center">
									<span className="font-mono text-sm font-semibold">
										{signals.length}
									</span>
								</div>
							</div>
						</div>
						<div className="space-y-2 text-[10px] text-muted-foreground">
							{summaryPie.map((item) => (
								<div
									key={item.id}
									className="grid grid-cols-[8px_1fr_auto] items-center gap-1.5"
								>
									<span
										className="h-2 w-2 rounded-full"
										style={{ backgroundColor: item.color }}
									/>
									<span>{item.id}</span>
									<span className="font-mono text-foreground">{item.value}</span>
								</div>
							))}
						</div>
					</div>
				</div>
			</div>

			<div className="border border-border rounded-md bg-card/30 overflow-hidden">
				<table className="w-full text-xs">
					<thead>
						<tr className="border-b border-border text-muted-foreground text-[10px] uppercase">
							<th className="text-left px-3 py-2">Rule</th>
							<th className="text-left px-3 py-2">Severity</th>
							<th className="text-right px-3 py-2">Findings</th>
							<th className="text-right px-3 py-2">Blocks</th>
							<th className="text-right px-3 py-2">Warns</th>
							<th className="text-right px-3 py-2">
								{tab === "fp"
									? "Allow After Warn"
									: tab === "fn"
										? "Errors"
										: "Decision Types"}
							</th>
							<th className="text-right px-3 py-2">Score</th>
							<th className="px-3 py-2 w-8" />
							<th className="px-3 py-2 text-right">
								{allActive.length > TABLE_DEFAULT_LIMIT && (
									<button
										type="button"
										onClick={() => setShowAll((v) => !v)}
										className="text-[10px] text-primary hover:underline whitespace-nowrap"
									>
										{showAll ? "Show less" : `Show all ${allActive.length}`}
									</button>
								)}
							</th>
						</tr>
					</thead>
					<tbody>
						{active.map((s) => (
							<tr
								key={s.rule_id}
								className="border-b border-border/50 hover:bg-muted/20 transition-colors"
							>
								<td
									className="px-3 py-1.5 font-medium"
									title={getRuleDescription(s.rule_id) || s.rule_id}
								>
									<div>{s.rule_id}</div>
									{getRuleDescription(s.rule_id) && (
										<div className="text-[10px] text-muted-foreground font-normal leading-tight mt-0.5">
											{getRuleDescription(s.rule_id)}
										</div>
									)}
								</td>
								<td className="px-3 py-1.5">
									<span
										className={cn(
											"text-[10px] px-1.5 py-0.5 rounded-sm",
											s.severity === "CRITICAL"
												? "bg-signal-block/20 text-signal-block"
												: s.severity === "HIGH"
													? "bg-severity-high/20 text-severity-high"
													: s.severity === "MEDIUM"
														? "bg-signal-ask/20 text-signal-ask"
														: "bg-muted text-muted-foreground",
										)}
									>
										{s.severity}
									</span>
								</td>
								<td className="px-3 py-1.5 text-right">{s.totalFindings}</td>
								<td className="px-3 py-1.5 text-right">{s.blockCount}</td>
								<td className="px-3 py-1.5 text-right">{s.warnCount}</td>
								<td className="px-3 py-1.5 text-right">
									{tab === "fp"
										? s.allowAfterWarn
										: tab === "fn"
											? s.errorOverride
											: `${Math.round(s.inconsistencyRate * 100)}%`}
								</td>
								<td className="px-3 py-1.5 text-right font-semibold">
									<span
										className={cn(
											tab === "fp" && s.fpScore > 40
												? "text-signal-ask"
												: tab === "fn" && s.fnScore > 30
													? "text-signal-block"
													: tab === "inconsistent" && s.inconsistencyRate > 0.5
														? "text-signal-error"
														: "text-foreground",
										)}
									>
										{tab === "inconsistent"
											? `${Math.round(s.inconsistencyRate * 100)}%`
											: Math.round(tab === "fp" ? s.fpScore : s.fnScore)}
									</span>
								</td>
								<td className="px-3 py-1.5">
									<FlagButton
										itemType="rule"
										itemId={s.rule_id}
										label={`Rule ${s.rule_id} (${tab === "fp" ? "FP" : tab === "fn" ? "FN" : "noisy"} suspect, score ${Math.round(s.fpScore)})`}
										compact
									/>
								</td>
								<td /> {/* show all column spacer */}
							</tr>
						))}
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
