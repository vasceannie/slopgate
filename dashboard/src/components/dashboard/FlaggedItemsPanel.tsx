import { useState, useMemo, useCallback } from "react";
import { cn } from "@/lib/utils";
import { Flag, Download, Check, X, Target, Clock, Radio, Trash2 } from "lucide-react";
import { useFlagSystem } from "@/context/FlagContext";
import { FLAG_TARGET_LABELS } from "@/lib/chartTheme";
import type { InvestigationFlag, FlagTarget } from "@/types/slopgate";

export function FlaggedItemsPanel() {
  const { flags, resolveFlag, unresolveFlag, removeFlag, exportFlags } = useFlagSystem();
  const [showResolved, setShowResolved] = useState(false);

  const active = useMemo(() => flags.filter(f => !f.resolved), [flags]);
  const resolved = useMemo(() => flags.filter(f => f.resolved), [flags]);
  const displayed = showResolved ? resolved : active;

  const handleExport = useCallback(() => {
    const text = exportFlags();
    const blob = new Blob([text], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `slopgate-flags-${new Date().toISOString().slice(0, 10)}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  }, [exportFlags]);

  if (flags.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
        <Flag className="w-6 h-6 mb-2 opacity-40" />
        <div className="text-xs">No flagged items yet</div>
        <div className="text-[10px] mt-1">Click the flag icon on any event, rule, path, or session to flag it</div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex gap-1">
          <button
            onClick={() => setShowResolved(false)}
            className={cn("px-2 py-0.5 text-[10px] rounded-sm transition-colors uppercase",
              !showResolved ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted")}
          >
            Active ({active.length})
          </button>
          <button
            onClick={() => setShowResolved(true)}
            className={cn("px-2 py-0.5 text-[10px] rounded-sm transition-colors uppercase",
              showResolved ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted")}
          >
            Resolved ({resolved.length})
          </button>
        </div>
        <button
          onClick={handleExport}
          className="flex items-center gap-1 px-2 py-0.5 text-[10px] text-muted-foreground hover:text-foreground transition-colors"
        >
          <Download className="w-3 h-3" /> Export
        </button>
      </div>

      <div className="border border-border rounded-md bg-card/30 overflow-hidden divide-y divide-border/30">
        {displayed.map(flag => (
          <FlagRow
            key={flag.id}
            flag={flag}
            onResolve={() => resolveFlag(flag.id)}
            onUnresolve={() => unresolveFlag(flag.id)}
            onRemove={() => removeFlag(flag.id)}
          />
        ))}
      </div>
    </div>
  );
}

function FlagRow({ flag, onResolve, onUnresolve, onRemove }: {
  flag: InvestigationFlag;
  onResolve: () => void;
  onUnresolve: () => void;
  onRemove: () => void;
}) {
  const ModeIcon = flag.mode === "on-direction" ? Target : flag.mode === "cron" ? Clock : Radio;

  return (
    <div className={cn("px-3 py-2 text-xs", flag.resolved && "opacity-50")}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 min-w-0">
          <Flag className="w-3 h-3 text-signal-ask shrink-0" fill={flag.resolved ? "none" : "currentColor"} />
          <span className={cn("font-medium", FLAG_TARGET_LABELS[flag.target].color)}>{FLAG_TARGET_LABELS[flag.target].label}</span>
          <span className="text-muted-foreground">·</span>
          <span className="text-[10px] px-1 py-0.5 bg-muted rounded uppercase">{flag.itemType}</span>
          <span className="font-mono truncate">{flag.itemId}</span>
        </div>
        <div className="flex items-center gap-1 shrink-0 ml-2">
          <ModeIcon className="w-3 h-3 text-muted-foreground" />
          <span className="text-[10px] text-muted-foreground">{flag.mode}</span>
          {flag.resolved ? (
            <button onClick={onUnresolve} className="ml-1 text-muted-foreground hover:text-signal-ask" title="Reopen">
              <X className="w-3 h-3" />
            </button>
          ) : (
            <button onClick={onResolve} className="ml-1 text-muted-foreground hover:text-primary" title="Resolve">
              <Check className="w-3 h-3" />
            </button>
          )}
          <button onClick={onRemove} className="text-muted-foreground hover:text-signal-block" title="Delete">
            <Trash2 className="w-3 h-3" />
          </button>
        </div>
      </div>
      <div className="text-[10px] text-muted-foreground mt-0.5 ml-5">{flag.label}</div>
      {flag.notes && <div className="text-[10px] text-foreground/70 mt-0.5 ml-5 italic">"{flag.notes}"</div>}
      <div className="text-[10px] text-muted-foreground/60 mt-0.5 ml-5">
        {new Date(flag.createdAt).toLocaleString()}
      </div>
    </div>
  );
}