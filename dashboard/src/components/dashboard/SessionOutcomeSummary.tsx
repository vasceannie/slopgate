import { AlertOctagon, CheckCircle2, ShieldAlert } from "lucide-react";
import { PLATFORM_BADGE_STYLE } from "@/lib/chartTheme";
import type { SessionData } from "@/lib/sessionHelpers";
import { primarySessionCause, sessionActivitySummary } from "@/lib/sessionHelpers";
import { cn } from "@/lib/utils";

interface SessionOutcomeSummaryProps {
  session: SessionData;
}

export function SessionOutcomeSummary({ session }: SessionOutcomeSummaryProps) {
  const cause = primarySessionCause(session);
  const activity = sessionActivitySummary(session);
  const toolSummary = activity.lastTool
    ? activity.toolCount > 1
      ? `${activity.lastTool} (+${activity.toolCount - 1})`
      : activity.lastTool
    : "None";

  const isBlocked = cause.decision === "block" || cause.decision === "deny";
  const isAdvisory = cause.decision !== "block" && cause.decision !== "deny" && cause.decision !== "allow";

  return (
    <div className="bg-card/25 border-b border-border/60 px-4 py-3 text-xs select-none transition-all duration-300 hover:bg-card/30">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-2.5 min-w-0">
          {isBlocked ? (
            <div className="flex items-center justify-center w-6 h-6 rounded bg-signal-deny/10 text-signal-deny border border-signal-deny/20 transition-transform duration-200 hover:scale-105">
              <AlertOctagon className="w-4 h-4" />
            </div>
          ) : isAdvisory ? (
            <div className="flex items-center justify-center w-6 h-6 rounded bg-signal-ask/10 text-signal-ask border border-signal-ask/20 transition-transform duration-200 hover:scale-105">
              <ShieldAlert className="w-4 h-4" />
            </div>
          ) : (
            <div className="flex items-center justify-center w-6 h-6 rounded bg-signal-allow/10 text-signal-allow border border-signal-allow/20 transition-transform duration-200 hover:scale-105">
              <CheckCircle2 className="w-4 h-4" />
            </div>
          )}
          <div className="min-w-0">
            <div className="font-semibold text-foreground text-sm flex items-center gap-2">
              {isBlocked ? (
                <span className="text-signal-deny uppercase">Blocked Session</span>
              ) : isAdvisory ? (
                <span className="text-signal-ask uppercase">Advisory Warnings</span>
              ) : (
                <span className="text-signal-allow uppercase">Clean Allow</span>
              )}
              <span className="text-muted-foreground text-xs font-normal">({session.id.slice(0, 16)}…)</span>
            </div>
            <div className="text-muted-foreground text-[11px] mt-0.5 truncate">
              {isBlocked ? (
                <span>
                  Blocked by rule <strong className="text-foreground">{cause.ruleId}</strong>: {cause.message}
                </span>
              ) : isAdvisory ? (
                <span>
                  Advisory findings triggered by <strong className="text-foreground">{cause.ruleId}</strong>: {cause.message}
                </span>
              ) : (
                <span>All guardrails passed cleanly. No blocking rules fired.</span>
              )}
            </div>
          </div>
        </div>

        <div className="flex flex-wrap gap-x-6 gap-y-1.5 text-[11px] text-muted-foreground ml-auto pr-2">
          <div>
            Platform:{" "}
            <span className={cn("px-1.5 py-0.5 rounded text-[10px] uppercase font-medium", PLATFORM_BADGE_STYLE[session.platform])}>
              {session.platform}
            </span>
          </div>
          <div>
            Tools: <span className="text-foreground font-medium">{toolSummary}</span>
          </div>
          <div>
            Events: <span className="text-foreground font-medium">{activity.eventCount}</span>
          </div>
          <div>
            Duration:{" "}
            <span className="text-foreground font-medium">
              {session.duration > 60000 ? `${(session.duration / 60000).toFixed(1)}m` : `${(session.duration / 1000).toFixed(0)}s`}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
