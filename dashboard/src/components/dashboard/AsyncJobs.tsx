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
const PASS_COLOR = "hsl(142, 50%, 45%)";
const FAIL_COLOR = "hsl(0, 72%, 51%)";

export function AsyncJobs({ passCount, failCount, byCommand }: Props) {
	const [expandedCmd, setExpandedCmd] = useState<string | null>(null);

	const totalJobs = passCount + failCount;
	const passPercent = totalJobs ? Math.round((passCount / totalJobs) * 100) : 0;

	const runtimeData = byCommand
		.sort((a, b) => b.medianRuntime - a.medianRuntime)
		.slice(0, 8)
		.map((c) => ({
			command: c.command.length > 20 ? `${c.command.slice(0, 18)}…` : c.command,
			runtime: Math.round(c.medianRuntime),
		}));
	const maxRuntime = Math.max(...runtimeData.map((row) => row.runtime), 1);

	const noisy = [...byCommand]
		.filter((c) => c.fail > 0)
		.sort((a, b) => b.fail / b.total - a.fail / a.total)
		.slice(0, 5);

	return (
		<div className="space-y-4">
			<h3 className="text-xs text-muted-foreground uppercase tracking-wider px-1">
				Async Jobs / Quality Follow-up
			</h3>

			<div className="grid grid-cols-2 gap-3">
				<div className="border border-border rounded-md bg-card/30 p-2">
					<h4 className="text-[10px] text-muted-foreground uppercase mb-1 text-center">
						Pass / Fail
					</h4>
					<div className="h-[150px]">
						<div className="flex h-full items-center justify-center gap-4">
							<div
								className="grid h-24 w-24 place-items-center rounded-full"
								style={{
									background: `conic-gradient(${PASS_COLOR} 0 ${passPercent}%, ${FAIL_COLOR} ${passPercent}% 100%)`,
								}}
								title={`${passCount} passed, ${failCount} failed`}
							>
								<div className="grid h-14 w-14 place-items-center rounded-full bg-card text-center">
									<span className="font-mono text-sm font-semibold">
										{passPercent}%
									</span>
								</div>
							</div>
							<div className="space-y-2 text-[10px] text-muted-foreground">
								<LegendItem color={PASS_COLOR} label="Pass" value={passCount} />
								<LegendItem color={FAIL_COLOR} label="Fail" value={failCount} />
							</div>
						</div>
					</div>
				</div>

				<div className="border border-border rounded-md bg-card/30 p-2">
					<h4 className="text-[10px] text-muted-foreground uppercase mb-1 text-center">
						Median Runtime (ms)
					</h4>
					<div className="flex h-[150px] flex-col justify-center gap-1.5">
						{runtimeData.map((row) => (
							<div
								key={row.command}
								className="grid grid-cols-[minmax(0,1fr)_minmax(80px,1.8fr)_42px] items-center gap-2 text-[10px]"
								title={`${row.command}: ${row.runtime}ms median`}
							>
								<span className="truncate font-mono text-muted-foreground">
									{row.command}
								</span>
								<div className="h-2 rounded-sm bg-muted/40">
									<div
										className="h-full rounded-sm bg-primary"
										style={{
											width: `${Math.max(
												1,
												(row.runtime / maxRuntime) *
													RUNTIME_BAR_MAX_WIDTH_PERCENT,
											)}%`,
										}}
									/>
								</div>
								<span className="text-right font-mono text-foreground">
									{row.runtime}
								</span>
							</div>
						))}
						{runtimeData.length === 0 && (
							<div className="text-center text-xs text-muted-foreground">
								No async runtime data
							</div>
						)}
					</div>
				</div>
			</div>

			<div className="border border-border rounded-md bg-card/30 p-3">
				<h4 className="text-[10px] text-muted-foreground uppercase tracking-wider mb-2">
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
								<span className="font-mono truncate">{c.command}</span>
								<div className="flex items-center gap-3 shrink-0">
									<span className="text-signal-deny">
										{((c.fail / c.total) * 100).toFixed(0)}% fail
									</span>
									<span className="text-muted-foreground">{c.total} runs</span>
								</div>
							</button>
							{expandedCmd === c.command && c.failures.length > 0 && (
								<pre className="mx-2 mt-1 mb-2 p-2 rounded-sm bg-background text-[10px] text-signal-deny/80 overflow-x-auto whitespace-pre-wrap border border-border">
									{c.failures.join("\n---\n")}
								</pre>
							)}
						</div>
					))}
					{noisy.length === 0 && (
						<div className="text-xs text-muted-foreground">
							No failing commands
						</div>
					)}
				</div>
			</div>
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
		<div className="flex items-center gap-2">
			<span
				className="h-2 w-2 rounded-full"
				style={{ backgroundColor: color }}
			/>
			<span className="min-w-8">{label}</span>
			<span className="font-mono text-foreground">{value}</span>
		</div>
	);
}
