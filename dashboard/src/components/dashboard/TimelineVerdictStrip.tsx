import { AlertOctagon, CheckCircle2, ShieldAlert } from "lucide-react";
import { DECISION_BADGE_STYLE } from "@/lib/chartTheme";
import type { TimelineEntry } from "@/lib/sessionHelpers";
import { cn } from "@/lib/utils";

interface TimelineVerdictStripProps {
	entry: TimelineEntry;
}

export function TimelineVerdictStrip({ entry }: TimelineVerdictStripProps) {
	const isBlocked = entry.decision === "block" || entry.decision === "deny";
	const isAdvisory =
		entry.decision !== "block" &&
		entry.decision !== "deny" &&
		entry.decision !== "allow" &&
		entry.decision !== undefined;

	return (
		<div className="bg-muted/10 border border-border/40 rounded-md p-3 mb-3 text-xs select-none">
			<div className="flex items-start gap-2.5">
				{isBlocked ? (
					<AlertOctagon className="w-5 h-5 text-signal-deny shrink-0 mt-0.5" />
				) : isAdvisory ? (
					<ShieldAlert className="w-5 h-5 text-signal-ask shrink-0 mt-0.5" />
				) : (
					<CheckCircle2 className="w-5 h-5 text-signal-allow shrink-0 mt-0.5" />
				)}
				<div className="flex-1 min-w-0">
					<div className="flex items-center justify-between gap-2 flex-wrap">
						<span className="font-semibold text-foreground text-sm">
							{entry.label} {entry.type === "hook" ? "Hook Decision" : "Result"}
						</span>
						{entry.decision && (
							<span
								className={cn(
									"px-1.5 py-0.5 rounded border text-[10px] uppercase font-bold",
									DECISION_BADGE_STYLE[entry.decision],
								)}
							>
								{entry.decision}
							</span>
						)}
					</div>
					<div className="text-muted-foreground text-[11px] mt-1 space-y-1">
						{entry.detail && (
							<p>
								<span className="text-muted-foreground/80 font-normal">Source:</span>{" "}
								<span className="text-foreground">{entry.detail}</span>
							</p>
						)}
						{entry.toolName && (
							<p>
								<span className="text-muted-foreground/80 font-normal">Tool:</span>{" "}
								<span className="text-foreground font-semibold">{entry.toolName}</span>
							</p>
						)}
						{entry.candidate_paths && entry.candidate_paths.length > 0 && (
							<p className="truncate" title={entry.candidate_paths.join(", ")}>
								<span className="text-muted-foreground/80 font-normal">Paths:</span>{" "}
								<span className="text-foreground font-mono">
									{entry.candidate_paths.join(", ")}
								</span>
							</p>
						)}
					</div>
				</div>
			</div>
		</div>
	);
}
