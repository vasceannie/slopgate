import { DECISION_COLORS } from "@/lib/chartTheme";
import type {
	Decision,
	EventName,
	Platform,
	TimeWindow,
} from "@/types/slopgate";

interface Props {
	timeSeries: Array<{ time: string } & Record<Decision, number>>;
	eventsByType: Record<string, number>;
	eventsByTypeAndPlatform: Record<EventName, Partial<Record<Platform, number>>>;
	timeWindow?: TimeWindow;
}

const DECISION_LANES: Decision[] = [
	"context",
	"warn",
	"ask",
	"block",
	"deny",
	"allow",
];
const PIPELINE_STAGES: EventName[] = [
	"SessionStart",
	"PreToolUse",
	"PermissionRequest",
	"PostToolUse",
	"Stop",
];
const PIPELINE_PLATFORMS: Platform[] = ["claude", "codex", "opencode"];

const PIPELINE_CELL_BASE =
	"rounded-sm border border-border/70 px-1.5 py-1 text-center font-mono leading-none";
const PIPELINE_CELL_CLASSES: Record<
	Platform,
	readonly [string, string, string, string]
> = {
	claude: [
		"bg-platform-claude/5 text-muted-foreground",
		"bg-platform-claude/20 text-platform-claude",
		"bg-platform-claude/40 text-foreground",
		"bg-platform-claude/60 text-foreground",
	],
	codex: [
		"bg-platform-codex/5 text-muted-foreground",
		"bg-platform-codex/20 text-platform-codex",
		"bg-platform-codex/40 text-foreground",
		"bg-platform-codex/60 text-foreground",
	],
	opencode: [
		"bg-platform-opencode/5 text-muted-foreground",
		"bg-platform-opencode/20 text-platform-opencode",
		"bg-platform-opencode/40 text-foreground",
		"bg-platform-opencode/60 text-foreground",
	],
};

const LANE_CHART_HEIGHT = 22;
const LANE_CHART_WIDTH = 100;
const LANE_VALUE_WIDTH = 112;
const COUNT_THOUSAND = 1000;
const COUNT_TEN_THOUSAND = 10000;
const COUNT_MILLION = 1000000;
const PIPELINE_CLASS_BUCKETS = 3;

/** Format an ISO date string based on the time window granularity */
function formatAxisLabel(time: string, window: TimeWindow): string {
	const d = new Date(time);
	if (window === "1h") {
		// Tight window: show hour + minute
		return d.toLocaleDateString("en-US", {
			hour: "numeric",
			minute: "2-digit",
		});
	}
	if (window === "6h") {
		// Today-anchored: show month, day, hour
		return d.toLocaleDateString("en-US", {
			month: "short",
			day: "numeric",
			hour: "numeric",
		});
	}
	// 7d / 30d: date only — time is homogeneous
	return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function formatCompactCount(value: number): string {
	if (value >= COUNT_MILLION) return `${(value / COUNT_MILLION).toFixed(1)}M`;
	if (value >= COUNT_THOUSAND) {
		return `${(value / COUNT_THOUSAND).toFixed(value >= COUNT_TEN_THOUSAND ? 0 : 1)}k`;
	}
	return value.toLocaleString();
}

function formatEventLabel(stage: EventName): string {
	return stage.replace(/([A-Z])/g, " $1").trim();
}

function getPipelineCellClass(
	platform: Platform,
	value: number,
	maxValue: number,
): string {
	const bucket =
		value === 0 || maxValue === 0
			? 0
			: Math.max(1, Math.ceil((value / maxValue) * PIPELINE_CLASS_BUCKETS));
	const bucketClass =
		PIPELINE_CELL_CLASSES[platform][bucket] ??
		PIPELINE_CELL_CLASSES[platform][0];
	return `${PIPELINE_CELL_BASE} ${bucketClass}`;
}

function buildLanePoints(values: number[]): {
	max: number;
	latest: number;
	points: string;
} {
	const max = Math.max(...values, 0);
	const latest = values.at(-1) ?? 0;

	if (values.length === 0) return { max: 0, latest: 0, points: "" };
	if (values.length === 1) {
		const y = max === 0 ? LANE_CHART_HEIGHT : 0;
		return { max, latest, points: `0,${y} ${LANE_CHART_WIDTH},${y}` };
	}

	const denominator = Math.max(values.length - 1, 1);
	const points = values
		.map((value, index) => {
			const x = (index / denominator) * LANE_CHART_WIDTH;
			const y =
				max === 0
					? LANE_CHART_HEIGHT
					: LANE_CHART_HEIGHT - (value / max) * LANE_CHART_HEIGHT;
			return `${x.toFixed(2)},${y.toFixed(2)}`;
		})
		.join(" ");

	return { max, latest, points };
}

export function DecisionFunnel({
	timeSeries,
	eventsByType,
	eventsByTypeAndPlatform,
	timeWindow = "7d",
}: Props) {
	const decisionLanes = DECISION_LANES.map((decision) => {
		const values = timeSeries.map((t) => t[decision] || 0);
		return {
			decision,
			color: DECISION_COLORS[decision],
			...buildLanePoints(values),
		};
	});

	const axisLabels =
		timeSeries.length > 0
			? [
					formatAxisLabel(timeSeries[0]?.time, timeWindow),
					formatAxisLabel(
						timeSeries[Math.floor((timeSeries.length - 1) / 2)]?.time,
						timeWindow,
					),
					formatAxisLabel(timeSeries[timeSeries.length - 1]?.time, timeWindow),
				]
			: [];

	const pipelineRows = PIPELINE_STAGES.map((stage) => ({
		stage,
		label: formatEventLabel(stage),
		total: eventsByType[stage] ?? 0,
		harnesses: PIPELINE_PLATFORMS.map((platform) => ({
			platform,
			value: eventsByTypeAndPlatform[stage]?.[platform] ?? 0,
		})),
	})).sort((a, b) => b.total - a.total);
	const maxPipelineCell = Math.max(
		...pipelineRows.flatMap((row) => row.harnesses.map((cell) => cell.value)),
		0,
	);

	return (
		<div className="grid min-h-[590px] gap-4 lg:h-[650px] lg:grid-rows-[minmax(260px,1.12fr)_minmax(220px,0.88fr)]">
			<div>
				<h3 className="text-xs text-muted-foreground uppercase tracking-wider mb-2 px-1">
					Decision Volume Over Time
				</h3>
				<div className="h-[calc(100%-1.25rem)] min-h-[260px] border border-border rounded-md bg-card/30 p-3">
					{timeSeries.length > 0 ? (
						<div className="grid h-full grid-rows-[1fr_auto] gap-2">
							<div className="grid content-around gap-2">
								{decisionLanes.map((lane) => (
									<div
										key={lane.decision}
										className="grid grid-cols-[68px_minmax(0,1fr)_112px] items-center gap-2 text-[9px]"
									>
										<div className="flex items-center gap-1.5 uppercase tracking-wide text-muted-foreground">
											<span
												className="h-1.5 w-1.5 rounded-full"
												style={{ backgroundColor: lane.color }}
											/>
											<span>{lane.decision}</span>
										</div>
										<svg
											viewBox={`0 0 ${LANE_CHART_WIDTH} ${LANE_CHART_HEIGHT}`}
											preserveAspectRatio="none"
											className="h-6 w-full overflow-visible"
											role="img"
											aria-label={`${lane.decision} trend, latest ${lane.latest.toLocaleString()}, max ${lane.max.toLocaleString()}`}
										>
											<line
												x1="0"
												y1={LANE_CHART_HEIGHT}
												x2={LANE_CHART_WIDTH}
												y2={LANE_CHART_HEIGHT}
												stroke="hsl(220, 15%, 15%)"
												strokeWidth="0.8"
											/>
											{lane.points && (
												<polyline
													points={lane.points}
													fill="none"
													stroke={lane.color}
													strokeWidth="1.8"
													vectorEffect="non-scaling-stroke"
													strokeLinecap="round"
													strokeLinejoin="round"
												/>
											)}
										</svg>
										<div
											className="grid text-right font-mono leading-none"
											style={{ width: LANE_VALUE_WIDTH }}
										>
											<span className="text-foreground">
												{formatCompactCount(lane.latest)}
											</span>
											<span className="text-[8px] text-muted-foreground">
												max {formatCompactCount(lane.max)}
											</span>
										</div>
									</div>
								))}
							</div>
							<div className="grid grid-cols-[68px_minmax(0,1fr)_112px] gap-2 text-[9px] text-muted-foreground">
								<span />
								<div className="flex justify-between px-0.5">
									{axisLabels.map((label) => (
										<span key={label}>{label}</span>
									))}
								</div>
								<span className="text-right">independent scale</span>
							</div>
						</div>
					) : (
						<div className="flex items-center justify-center h-full text-muted-foreground text-xs">
							No data in window
						</div>
					)}
				</div>
			</div>

			<div>
				<h3 className="text-xs text-muted-foreground uppercase tracking-wider mb-2 px-1">
					Event Pipeline
				</h3>
				<div className="h-[calc(100%-1.25rem)] min-h-[220px] border border-border rounded-md bg-card/30 p-3">
					{pipelineRows.some((row) => row.total > 0) ? (
						<div className="grid h-full grid-rows-[auto_1fr_auto] gap-2">
							<div className="grid grid-cols-[minmax(104px,1fr)_58px_repeat(3,minmax(54px,70px))] gap-1.5 text-[8px] uppercase tracking-wide text-muted-foreground">
								<span>event</span>
								<span className="text-right">total</span>
								{PIPELINE_PLATFORMS.map((platform) => (
									<span key={platform} className="text-center">
										{platform}
									</span>
								))}
							</div>
							<div className="grid content-around gap-2">
								{pipelineRows.map((row) => (
									<div
										key={row.stage}
										className="grid grid-cols-[minmax(104px,1fr)_58px_repeat(3,minmax(54px,70px))] items-center gap-1.5 text-[9px]"
									>
										<span className="truncate text-muted-foreground">
											{row.label}
										</span>
										<span className="text-right font-mono text-foreground">
											{formatCompactCount(row.total)}
										</span>
										{row.harnesses.map((cell) => (
											<div
												key={`${row.stage}-${cell.platform}`}
												className={getPipelineCellClass(
													cell.platform,
													cell.value,
													maxPipelineCell,
												)}
												title={`${row.label} · ${cell.platform}: ${cell.value.toLocaleString()}`}
											>
												{formatCompactCount(cell.value)}
											</div>
										))}
									</div>
								))}
							</div>
							<div className="flex items-center justify-between pt-1 text-[8px] text-muted-foreground">
								<span>cell intensity = harness count</span>
								<span>event × harness matrix</span>
							</div>
						</div>
					) : (
						<div className="flex items-center justify-center h-full text-muted-foreground text-xs">
							No data in window
						</div>
					)}
				</div>
			</div>
		</div>
	);
}
