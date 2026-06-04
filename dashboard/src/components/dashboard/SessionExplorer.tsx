import { useState, useCallback, memo } from "react";
import { cn } from "@/lib/utils";
import { ChevronDown, ChevronRight, Copy, Check } from "lucide-react";
import { SessionTimeline } from "./SessionTimeline";
import { FlagButton } from "./FlagButton";
import { DECISION_BADGE_STYLE, PLATFORM_BADGE_STYLE } from "@/lib/chartTheme";
import type { Decision, Platform, HookEvent, RuleFinding, HookResult, SubprocessRun } from "@/types/slopgate";

export interface SessionData {
  id: string;
  platform: Platform;
  eventCount: number;
  tools: string[];
  languages: string[];
  pathCount: number;
  finalOutcome: Decision;
  duration: number;
  events: HookEvent[];
  findings: RuleFinding[];
  results: HookResult[];
  subprocesses: SubprocessRun[];
}

interface Props {
  sessions: SessionData[];
}

export function SessionExplorer({ sessions }: Props) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const perPage = 15;
  const paginated = sessions.slice(page * perPage, (page + 1) * perPage);

  const copyId = useCallback((id: string) => {
    navigator.clipboard.writeText(id);
    setCopied(id);
    setTimeout(() => setCopied(null), 1500);
  }, []);

  return (
    <div className="space-y-2">
      <h3 className="text-xs text-muted-foreground uppercase tracking-wider px-1">Session & Tool Explorer</h3>
      <div className="border border-border rounded-md bg-card/30 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border text-muted-foreground">
                <th className="px-3 py-2 text-left w-8" />
                <th className="px-3 py-2 text-left">Session</th>
                <th className="px-3 py-2 text-left">Platform</th>
                <th className="px-3 py-2 text-center">Events</th>
                <th className="px-3 py-2 text-left">Tools</th>
                <th className="px-3 py-2 text-left">Languages</th>
                <th className="px-3 py-2 text-left">Paths</th>
                <th className="px-3 py-2 text-center">Outcome</th>
                <th className="px-3 py-2 text-right">Duration</th>
                <th className="px-3 py-2 w-8" />
              </tr>
            </thead>
            <tbody>
              {paginated.map(s => (
                <SessionRow
                  key={s.id}
                  session={s}
                  isExpanded={expanded === s.id}
                  isCopied={copied === s.id}
                  onToggle={() => setExpanded(expanded === s.id ? null : s.id)}
                  onCopy={() => copyId(s.id)}
                />
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex items-center justify-between px-3 py-2 border-t border-border text-[10px] text-muted-foreground">
          <span>{sessions.length} sessions</span>
          <div className="flex gap-2">
            <button disabled={page === 0} onClick={() => setPage(p => p - 1)} className="hover:text-foreground disabled:opacity-30">← Prev</button>
            <span>{page + 1}/{Math.max(1, Math.ceil(sessions.length / perPage))}</span>
            <button disabled={(page + 1) * perPage >= sessions.length} onClick={() => setPage(p => p + 1)} className="hover:text-foreground disabled:opacity-30">Next →</button>
          </div>
        </div>
      </div>
    </div>
  );
}

const SessionRow = memo(function SessionRow({ session: s, isExpanded, isCopied, onToggle, onCopy }: {
  session: SessionData; isExpanded: boolean; isCopied: boolean; onToggle: () => void; onCopy: () => void;
}) {
  return (
    <>
      <tr
        className={cn(
          "border-b border-border/50 hover:bg-muted/20 cursor-pointer transition-colors",
          isExpanded && "bg-muted/10"
        )}
        onClick={onToggle}
      >
        <td className="px-3 py-2">
          {isExpanded ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
        </td>
        <td className="px-3 py-2 font-mono">
          <span className="flex items-center gap-1">
            {s.id.slice(0, 16)}…
            <button onClick={e => { e.stopPropagation(); onCopy(); }} className="hover:text-primary">
              {isCopied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
            </button>
          </span>
        </td>
        <td className="px-3 py-2">
          <span className={cn("px-1.5 py-0.5 rounded text-[10px] uppercase", PLATFORM_BADGE_STYLE[s.platform])}>{s.platform}</span>
        </td>
        <td className="px-3 py-2 text-center">{s.eventCount}</td>
        <td className="px-3 py-2">
          <div className="flex gap-1 flex-wrap max-w-[200px]">
            {s.tools.slice(0, 4).map(t => (
              <span key={t} className="px-1.5 py-0.5 bg-muted rounded text-[10px]">{t}</span>
            ))}
            {s.tools.length > 4 && <span className="text-muted-foreground">+{s.tools.length - 4}</span>}
          </div>
        </td>
        <td className="px-3 py-2">
          <span className="text-muted-foreground">{s.languages.join(", ")}</span>
        </td>
        <td className="px-3 py-2">
          <div className="flex gap-1 flex-wrap max-w-[200px]">
            {[...new Set(s.events.flatMap(e => e.candidate_paths ?? []))].slice(0, 3).map(p => (
              <span key={p} className="px-1 py-0.5 bg-muted rounded text-[10px] font-mono truncate max-w-[120px]" title={p}>{p.split("/").pop()}</span>
            ))}
            {s.pathCount > 3 && <span className="text-muted-foreground text-[10px]">+{s.pathCount - 3}</span>}
          </div>
        </td>
        <td className="px-3 py-2 text-center">
          <span className={cn("px-1.5 py-0.5 rounded border text-[10px] uppercase", DECISION_BADGE_STYLE[s.finalOutcome])}>{s.finalOutcome}</span>
        </td>
        <td className="px-3 py-2 text-right text-muted-foreground">
          {s.duration > 60000 ? `${(s.duration / 60000).toFixed(1)}m` : `${(s.duration / 1000).toFixed(0)}s`}
        </td>
        <td className="px-3 py-2">
          <FlagButton itemType="session" itemId={s.id} label={`Session ${s.id.slice(0, 12)} (${s.platform}, ${s.finalOutcome})`} compact />
        </td>
      </tr>
      {isExpanded && (
        <tr>
          <td colSpan={10} className="p-0">
            <SessionTimeline session={s} />
          </td>
        </tr>
      )}
    </>
  );
});