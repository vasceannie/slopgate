import { useCallback } from "react";
import { useTraceDataSource } from "@/context/useTraceDataSource";
import { cn } from "@/lib/utils";
import type { FilterState, Platform, TimeWindow } from "@/types/slopgate";

const TIME_OPTIONS: { value: TimeWindow; label: string }[] = [
	{ value: "1h", label: "1h" },
	{ value: "6h", label: "6h" },
	{ value: "24h", label: "24h" },
	{ value: "7d", label: "7d" },
	{ value: "30d", label: "30d" },
];

const TIME_LOOKBACK_HOURS: Record<TimeWindow, number> = {
	"1h": 1,
	"6h": 6,
	"24h": 24,
	"7d": 168,
	"30d": 720,
};

const PLATFORM_OPTIONS: { value: Platform; label: string; color: string }[] = [
	{ value: "claude", label: "Claude", color: "bg-platform-claude" },
	{ value: "codex", label: "Codex", color: "bg-platform-codex" },
	{ value: "opencode", label: "OpenCode", color: "bg-platform-opencode" },
	{ value: "cursor", label: "Cursor", color: "bg-platform-cursor" },
	{ value: "unknown", label: "Unknown", color: "bg-platform-unknown" },
];

interface Props {
	filters: FilterState;
	onChange: (f: FilterState) => void;
}

export function TimeWindowSelector({ filters, onChange }: Props) {
	const { sourceMode, sourceMeta, refreshSnapshot } = useTraceDataSource();
	const togglePlatform = useCallback(
		(p: Platform) => {
			const current = filters.platforms;
			const next = current.includes(p)
				? current.filter((x) => x !== p)
				: [...current, p];
			onChange({ ...filters, platforms: next });
		},
		[filters, onChange],
	);

	const setTimeWindow = useCallback(
		(timeWindow: TimeWindow) => {
			onChange({ ...filters, timeWindow });
			const hours = TIME_LOOKBACK_HOURS[timeWindow];
			const loadedHours = sourceMeta.snapshotLookbackHours ?? 0;
			if (
				sourceMode !== "uploaded" &&
				(loadedHours < hours || sourceMeta.snapshotError)
			) {
				void refreshSnapshot(hours);
			}
		},
		[
			filters,
			onChange,
			refreshSnapshot,
			sourceMeta.snapshotError,
			sourceMeta.snapshotLookbackHours,
			sourceMode,
		],
	);

	return (
		<div className="flex items-center gap-6 py-3 border-b border-border bg-card/50">
			<div className="flex items-center gap-1">
				<span className="text-xs text-muted-foreground mr-2">WINDOW</span>
				{TIME_OPTIONS.map((opt) => (
					<button
						type="button"
						key={opt.value}
						onClick={() => setTimeWindow(opt.value)}
						className={cn(
							"px-3 py-1 text-xs rounded-sm transition-colors",
							filters.timeWindow === opt.value
								? "bg-primary text-primary-foreground"
								: "text-muted-foreground hover:text-foreground hover:bg-muted",
						)}
					>
						{opt.label}
					</button>
				))}
			</div>

			<div className="w-px h-5 bg-border" />

			<div className="flex items-center gap-1">
				<span className="text-xs text-muted-foreground mr-2">PLATFORM</span>
				<button
					type="button"
					onClick={() => onChange({ ...filters, platforms: [] })}
					className={cn(
						"px-3 py-1 text-xs rounded-sm transition-colors",
						filters.platforms.length === 0
							? "bg-muted text-foreground"
							: "text-muted-foreground hover:text-foreground hover:bg-muted",
					)}
				>
					All
				</button>
				{PLATFORM_OPTIONS.map((opt) => (
					<button
						type="button"
						key={opt.value}
						onClick={() => togglePlatform(opt.value)}
						className={cn(
							"px-3 py-1 text-xs rounded-sm transition-colors flex items-center gap-1.5",
							filters.platforms.includes(opt.value)
								? "bg-muted text-foreground"
								: "text-muted-foreground hover:text-foreground hover:bg-muted",
						)}
					>
						<span className={cn("w-2 h-2 rounded-full", opt.color)} />
						{opt.label}
					</button>
				))}
			</div>

			<div className="ml-auto flex items-center gap-2">
				<span className="w-2 h-2 rounded-full bg-primary animate-pulse-glow" />
				<span className="text-xs text-muted-foreground">LIVE</span>
			</div>
		</div>
	);
}
