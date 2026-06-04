import { useMemo, memo, useState } from "react";
import { cn } from "@/lib/utils";
import { resolveDecision } from "@/hooks/useTraceData";
import { DECISION_DOT_STYLE } from "@/lib/chartTheme";
import type { Decision } from "@/types/slopgate";
import type { SessionData } from "./SessionExplorer";
import { FlagButton } from "./FlagButton";

const PAGE_SIZE = 50;

export const SessionTimeline = memo(function SessionTimeline({ session }: { session: SessionData }) {
  const [page, setPage] = useState(0);

  const entries = useMemo(() => {
    const items: Array<{
      time: string;
      type: "event" | "finding" | "result" | "subprocess";
      label: string;
      detail: string;
      decision?: Decision;
      flagItemType: "event" | "finding" | "result" | "session";
      flagItemId: string;
      flagLabel: string;
    }> = [];

    for (const e of session.events) {
      const cp = e.candidate_paths ?? [];
      const pathInfo = cp.length > 0 ? ` → ${cp.join(", ")}` : "";
      items.push({
        time: e.timestamp, type: "event",
        label: e.event_name, detail: (e.tool_name ? `tool: ${e.tool_name}` : "session lifecycle") + pathInfo,
        flagItemType: "event", flagItemId: `${session.id}:${e.event_name}:${e.timestamp}`,
        flagLabel: `${e.event_name} in session ${session.id.slice(0, 12)}`,
      });
    }

    for (const f of session.findings) {
      const msg = f.message ?? "";
      const dec = f.decision ?? "context";
      items.push({
        time: f.timestamp, type: "finding",
        label: f.rule_id, detail: `${f.severity} → ${dec}: ${msg.slice(0, 80) || "(no message)"}`,
        decision: dec,
        flagItemType: "finding", flagItemId: `${session.id}:${f.rule_id}:${f.timestamp}`,
        flagLabel: `${f.rule_id} (${f.severity} ${dec}) in session ${session.id.slice(0, 12)}`,
      });
    }

    for (const r of session.results) {
      const d = resolveDecision(r.findings);
      const errors = r.errors ?? [];
      items.push({
        time: r.timestamp, type: "result",
        label: `Result: ${d}`, detail: `${r.findings.length} findings, ${errors.length} errors`,
        decision: d,
        flagItemType: "result", flagItemId: `${session.id}:result:${r.timestamp}`,
        flagLabel: `Result ${d} in session ${session.id.slice(0, 12)}`,
      });
    }

    for (const s of session.subprocesses) {
      items.push({
        time: s.timestamp, type: "subprocess",
        label: s.command.slice(0, 40), detail: `exit ${s.returncode} (${s.duration_ms}ms)`,
        decision: s.returncode === 0 ? "allow" : "deny",
        flagItemType: "event", flagItemId: `${session.id}:subprocess:${s.timestamp}`,
        flagLabel: `${s.command.slice(0, 30)} (exit ${s.returncode}) in session ${session.id.slice(0, 12)}`,
      });
    }

    return items.sort((a, b) => a.time.localeCompare(b.time));
  }, [session]);

  const pageCount = Math.max(1, Math.ceil(entries.length / PAGE_SIZE));
  const pageEntries = entries.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  return (
    <div className="bg-background/50 border-t border-border max-h-[480px] overflow-y-auto">
      <div className="relative p-4 pl-10">
        <div className="absolute left-[21px] top-6 bottom-6 w-px bg-border" />
        {pageEntries.map((entry, i) => (
          <div key={i} className="relative flex items-start gap-3 mb-3 last:mb-0 group">
            <div className={cn(
              "absolute left-0 top-1.5 w-[7px] h-[7px] rounded-full border border-border z-10",
              entry.decision ? DECISION_DOT_STYLE[entry.decision] : "bg-muted-foreground"
            )} />
            <div className="ml-4 min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className={cn(
                  "text-[10px] uppercase px-1 py-0.5 rounded",
                  entry.type === "event" ? "bg-muted text-muted-foreground" :
                  entry.type === "finding" ? "bg-signal-ask/10 text-signal-ask" :
                  entry.type === "result" ? "bg-primary/10 text-primary" :
                  "bg-signal-warn/10 text-signal-warn"
                )}>
                  {entry.type}
                </span>
                <span className="text-xs font-medium truncate">{entry.label}</span>
                <div className="ml-auto flex items-center gap-1.5 shrink-0">
                  <FlagButton
                    itemType={entry.flagItemType}
                    itemId={entry.flagItemId}
                    label={entry.flagLabel}
                    compact
                  />
                  <span className="text-[10px] text-muted-foreground">
                    {new Date(entry.time).toLocaleTimeString()}
                  </span>
                </div>
              </div>
              <div className="text-[10px] text-muted-foreground mt-0.5 truncate">{entry.detail}</div>
            </div>
          </div>
        ))}
      </div>
      {pageCount > 1 && (
        <div className="flex items-center justify-between px-4 py-2 border-t border-border text-[10px] text-muted-foreground sticky bottom-0 bg-background/95 backdrop-blur-sm">
          <span>{entries.length} entries total</span>
          <div className="flex gap-2">
            <button disabled={page === 0} onClick={() => setPage(p => p - 1)} className="hover:text-foreground disabled:opacity-30">← Prev</button>
            <span>{page + 1} / {pageCount}</span>
            <button disabled={page + 1 >= pageCount} onClick={() => setPage(p => p + 1)} className="hover:text-foreground disabled:opacity-30">Next →</button>
          </div>
        </div>
      )}
    </div>
  );
});