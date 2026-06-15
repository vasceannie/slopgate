import { useState } from "react";

interface CommandStats {
	command: string;
	total: number;
	pass: number;
	fail: number;
	medianRuntime: number;
	failures: string[];
}

interface Props {
	passCount: number;
	failCount: number;
	byCommand: CommandStats[];
}

const RUNTIME_BAR_MAX_WIDTH_PERCENT = 100;
const PASS_COLOR = "hsl(var(--signal-allow))";
const FAIL_COLOR = "hsl(var(--signal-deny))";

function failureRate(command: CommandStats): number {
	return command.total > 0 ? command.fail / command.total : 0;
}

export function AsyncJobs({ passCount, failCount, byCommand }: Props) {
	const [expandedCmd, setExpandedCmd] = useState<string | null>(null);

	const totalJobs = passCount + failCount;
	const hasJobs = totalJobs > 0;
	const passPercent = hasJobs ? Math.round((passCount / totalJobs) * 100) : 0;
	const bg = hasJobs
		? `conic-gradient(${PASS_COLOR} 0 ${passPercent}%, ${FAIL_COLOR} ${passPercent}% 100%)`
		: "conic-gradient(hsl(var(--border)) 0 100%)";
	const passFailTitle = hasJobs
		? `${passCount} passed, ${failCount} failed`
		: "No async jobs ran in this window";
	const passFailLabel = hasJobs ? `${passPercent}%` : "idle";

	const maxRuntime = Math.max(...byCommand.map((c) => c.medianRuntime), 1);
	const runtimeData = [...byCommand]
		.sort((a, b) => b.medianRuntime - a.medianRuntime)
		.slice(0, 8)
		.map((c) => {
			const runtimeVal = Math.round(c.medianRuntime);
			const percent = Math.min(
				RUNTIME_BAR_MAX_WIDTH_PERCENT,
				Math.max(0, (runtimeVal / maxRuntime) * RUNTIME_BAR_MAX_WIDTH_PERCENT),
			);
			return {
				command: c.command,
				displayCommand: c.command.length > 20 ? `${c.command.slice(0, 18)}…` : c.command,
				runtime: runtimeVal,
				widthPercent: `${percent}%`,
			};
		});

	const noisy = [...byCommand]
		.filter((c) => c.fail > 0)
		.sort((a, b) => failureRate(b) - failureRate(a))
		.slice(0, 5);

	return (
		<div className="space-y-4">
			<h3 className="text-xs text-muted-foreground uppercase tracking-wider px-1">
				Async quality checks
			</h3>

			{!hasJobs ? (
				<div className="flex items-center justify-between gap-3 rounded-md border border-border/70 bg-card/20 px-3 py-2 text-left">
					<span className="text-xs font-semibold text-foreground">No async jobs ran in this window</span>
					<span className="text-[11px] text-muted-foreground/80">
						Trace logs show no background verification or linter check invocations.
					</span>
				</div>
			) : (
				<>
					<div className="grid grid-cols-2 gap-3">
						{/* Pass / Fail */}
						<div className="border border-border rounded-md bg-card/30 p-3">
							<h4 className="text-[11px] text-muted-foreground uppercase mb-2 text-center font-semibold tracking-wider">
								Pass / Fail
							</h4>
							<div className="h-[150px]">
								<div className="flex h-full items-center justify-center gap-4">
									<div
										aria-label={passFailTitle}
										className="grid h-24 w-24 place-items-center rounded-full shadow-inner"
										role="img"
										style={{background:bg}}
										title={passFailTitle}
									>
										<div className="grid h-14 w-14 place-items-center rounded-full bg-card text-center">
											<span className="font-mono text-xs font-semibold text-muted-foreground/85">
												{passFailLabel}
											</span>
										</div>
									</div>
									<div className="space-y-2 text-xs text-muted-foreground font-medium">
										<LegendItem color={PASS_COLOR} label="Pass" value={passCount} />
										<LegendItem color={FAIL_COLOR} label="Fail" value={failCount} />
									</div>
								</div>
							</div>
						</div>

						{/* Median Runtime */}
						<div className="border border-border rounded-md bg-card/30 p-3">
							<h4 className="text-[11px] text-muted-foreground uppercase mb-2 text-center font-semibold tracking-wider">
								Median Runtime (ms)
							</h4>
							<div className="flex h-[150px] flex-col justify-center gap-1.5">
								{runtimeData.map((row) => (
									<div
										key={row.command}
										className="grid grid-cols-[minmax(0,1.2fr)_minmax(60px,1.8fr)_40px] items-center gap-2 text-xs py-0.5 px-1 hover:bg-muted/10 rounded-sm transition-colors"
										title={`${row.command}: ${row.runtime}ms median`}
									>
										<span className="truncate font-mono text-muted-foreground" title={row.command}>
											{row.displayCommand}
										</span>
										<div className="h-1.5 rounded-sm bg-muted/40 overflow-hidden">
											<div
												className="h-full rounded-sm bg-primary transition-all duration-300"
												style={{width:row.widthPercent}}
											/>
										</div>
										<span className="text-right font-mono text-foreground">
											{row.runtime}
										</span>
									</div>
								))}
								{runtimeData.length === 0 && (
									<div className="px-4 py-8 text-center text-xs text-muted-foreground">
										No async jobs ran in this window
									</div>
								)}
							</div>
						</div>
					</div>

					{/* Noisy Commands */}
					<div className="border border-border rounded-md bg-card/30 p-3">
						<h4 className="text-[11px] text-muted-foreground uppercase tracking-wider mb-2 font-semibold">
							Noisy Commands (Highest Failure Rate)
						</h4>
						<div className="space-y-1">
							{noisy.map((c) => (
								<div key={c.command}>
									<button
										type="button"
										onClick={() =>
											setExpandedCmd(expandedCmd === c.command ? null : c.command)
										}
										className="w-full flex items-center justify-between px-2 py-1.5 rounded-sm hover:bg-muted/20 transition-colors text-xs"
									>
										<span className="font-mono break-all text-left mr-2">{c.command}</span>
										<div className="flex items-center gap-3 shrink-0">
											<span className="text-signal-deny font-medium">
												{(failureRate(c) * 100).toFixed(0)}% fail
											</span>
											<span className="text-muted-foreground">{c.total} runs</span>
										</div>
									</button>
									{expandedCmd === c.command && c.failures.length > 0 && (
										<pre className="mx-2 mt-1 mb-2 p-2 rounded-sm bg-background text-[11px] text-signal-deny/85 overflow-x-auto whitespace-pre-wrap break-all border border-border">
											{c.failures.join("\n---\n")}
										</pre>
									)}
								</div>
							))}
							{noisy.length === 0 && (
								<div className="px-2 py-3 text-center text-xs text-muted-foreground">
									No async command failures detected
								</div>
							)}
						</div>
					</div>
				</>
			)}
		</div>
	);
}

function LegendItem({
	color,
	label,
	value,
}: {
	color: string;
	label: string;
	value: number;
}) {
	return (
		<div className="flex items-center gap-2 text-xs">
			<span
				className="h-2.5 w-2.5 rounded-full"
				style={{backgroundColor:color}}
			/>
			<span className="min-w-8">{label}</span>
			<span className="font-mono text-foreground font-semibold">{value}</span>
		</div>
	);
}
