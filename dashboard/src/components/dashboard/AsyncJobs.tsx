import { ResponsiveBar } from "@nivo/bar";
import { ResponsivePie } from "@nivo/pie";
import { useState } from "react";
import { NIVO_DARK_THEME } from "@/lib/chartTheme";

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

export function AsyncJobs({ passCount, failCount, byCommand }: Props) {
	const [expandedCmd, setExpandedCmd] = useState<string | null>(null);

	const pieData = [
		{ id: "Pass", value: passCount, color: "hsl(142, 50%, 45%)" },
		{ id: "Fail", value: failCount, color: "hsl(0, 72%, 51%)" },
	];

	const runtimeData = byCommand
		.sort((a, b) => b.medianRuntime - a.medianRuntime)
		.slice(0, 8)
		.map((c) => ({
			command: c.command.length > 20 ? `${c.command.slice(0, 18)}…` : c.command,
			runtime: Math.round(c.medianRuntime),
		}));

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
						<ResponsivePie
							data={pieData}
							margin={{ top: 10, right: 10, bottom: 10, left: 10 }}
							innerRadius={0.6}
							colors={({ data }) => data.color}
							borderWidth={1}
							borderColor="hsl(220, 15%, 15%)"
							enableArcLinkLabels={false}
							arcLabelsTextColor="hsl(210, 20%, 95%)"
							theme={NIVO_DARK_THEME}
						/>
					</div>
				</div>

				<div className="border border-border rounded-md bg-card/30 p-2">
					<h4 className="text-[10px] text-muted-foreground uppercase mb-1 text-center">
						Median Runtime (ms)
					</h4>
					<div className="h-[150px]">
						<ResponsiveBar
							data={runtimeData}
							keys={["runtime"]}
							indexBy="command"
							layout="horizontal"
							margin={{ top: 5, right: 30, bottom: 5, left: 130 }}
							padding={0.3}
							colors="hsl(217, 91%, 60%)"
							enableLabel
							labelTextColor="hsl(210, 20%, 95%)"
							enableGridY={false}
							axisBottom={null}
							axisLeft={{ tickSize: 0, tickPadding: 8 }}
							theme={NIVO_DARK_THEME}
						/>
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
