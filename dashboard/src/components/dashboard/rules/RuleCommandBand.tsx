import { AlertTriangle, Check, ChevronDown, ChevronUp, Globe, Loader2, Plus, RotateCcw, Save, Wifi, WifiOff, X } from "lucide-react";
import { memo, useCallback, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useRulesConfig } from "@/context/useRulesConfig";
import { cn } from "@/lib/utils";
import type { RuleMetadata } from "@/types/slopgate";
import { getPendingChangesList } from "./model";

interface RuleCommandBandProps {
  allRules: RuleMetadata[];
}

interface TopBarStatusProps {
  apiAvailable: boolean;
  pendingCount: number;
  showPendingPanel: boolean;
  onTogglePendingPanel: () => void;
}

const TopBarStatus = memo(function TopBarStatus({ apiAvailable, pendingCount, showPendingPanel, onTogglePendingPanel }: TopBarStatusProps) {
  return (
    <div className="flex items-center gap-3">
      <Badge
        variant="outline"
        className={cn(
          "flex items-center gap-1.5 px-2.5 py-1 rounded text-[0.875rem] font-medium border animate-none",
          apiAvailable ? "bg-signal-allow/10 text-signal-allow border-signal-allow/25" : "bg-muted text-muted-foreground border-border",
        )}
      >
        {apiAvailable ? (
          <>
            <Wifi className="w-4 h-4 text-signal-allow animate-pulse" />
            API Connected
          </>
        ) : (
          <>
            <WifiOff className="w-4 h-4" />
            Read-Only (No API)
          </>
        )}
      </Badge>

      {pendingCount > 0 && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onTogglePendingPanel}
          className="flex items-center gap-1.5 px-2.5 h-7 rounded bg-signal-ask/10 text-signal-ask border-signal-ask/25 hover:bg-signal-ask/20 hover:text-signal-ask transition-colors text-[0.875rem] font-semibold"
        >
          <span>
            {pendingCount} Pending Change{pendingCount !== 1 ? "s" : ""}
          </span>
          {showPendingPanel ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
        </Button>
      )}
    </div>
  );
});

interface TopBarActionsProps {
  apiAvailable: boolean;
  pendingCount: number;
  saveStatus: string;
  saveError: string | null;
  onSave: () => void;
  onDiscard: () => void;
}

const TopBarActions = memo(function TopBarActions({
  apiAvailable,
  pendingCount,
  saveStatus,
  saveError,
  onSave,
  onDiscard,
}: TopBarActionsProps) {
  return (
    <div className="flex items-center gap-3">
      {pendingCount > 0 && (
        <>
          <Button
            type="button"
            onClick={onSave}
            disabled={saveStatus === "saving" || !apiAvailable}
            className="flex items-center gap-2 h-8 px-3 rounded bg-signal-allow text-white hover:bg-signal-allow/90 disabled:opacity-50 transition-colors text-[0.875rem] border-transparent font-semibold"
          >
            {saveStatus === "saving" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            Save to Littlebox
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={onDiscard}
            className="flex items-center gap-2 h-8 px-3 rounded bg-muted/50 text-muted-foreground hover:bg-muted transition-colors text-[0.875rem] font-semibold"
          >
            <RotateCcw className="w-4 h-4" />
            Discard
          </Button>
        </>
      )}

      {pendingCount === 0 && saveStatus === "saved" && (
        <span className="text-signal-allow flex items-center gap-1.5 text-[0.875rem]">
          <Check className="w-4 h-4" /> Config Saved
        </span>
      )}

      {saveStatus === "error" && saveError && (
        <span className="text-signal-block text-[0.875rem] flex items-center gap-1.5">
          <AlertTriangle className="w-4 h-4" /> {saveError}
        </span>
      )}
    </div>
  );
});

interface CommandTopBarProps {
  apiAvailable: boolean;
  pendingCount: number;
  showPendingPanel: boolean;
  onTogglePendingPanel: () => void;
  saveStatus: string;
  saveError: string | null;
  onSave: () => void;
  onDiscard: () => void;
}

const CommandTopBar = memo(function CommandTopBar({
  apiAvailable,
  pendingCount,
  showPendingPanel,
  onTogglePendingPanel,
  saveStatus,
  saveError,
  onSave,
  onDiscard,
}: CommandTopBarProps) {
  return (
    <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 py-2 border-b border-border">
      <TopBarStatus
        apiAvailable={apiAvailable}
        pendingCount={pendingCount}
        showPendingPanel={showPendingPanel}
        onTogglePendingPanel={onTogglePendingPanel}
      />
      <TopBarActions
        apiAvailable={apiAvailable}
        pendingCount={pendingCount}
        saveStatus={saveStatus}
        saveError={saveError}
        onSave={onSave}
        onDiscard={onDiscard}
      />
    </div>
  );
});

interface PendingChangesPanelProps {
  skipPathsChanged: boolean;
  pendingList: Array<{ rule_id: string; title: string; fields: string[] }>;
}

const PendingChangesPanel = memo(function PendingChangesPanel({ skipPathsChanged, pendingList }: PendingChangesPanelProps) {
  return (
    <div className="p-3 border border-signal-ask/30 bg-signal-ask/5 rounded-md space-y-2 transition-all animate-in fade-in slide-in-from-top-2 duration-200 ease-out-quart">
      <div className="text-[0.875rem] font-semibold text-signal-ask">Review Pending Modifications</div>
      <div className="max-h-48 overflow-y-auto space-y-1 divide-y divide-border">
        {skipPathsChanged && (
          <div className="py-1 flex items-center justify-between text-[0.875rem]">
            <span className="font-mono text-foreground font-medium">Global skip_paths</span>
            <span className="text-muted-foreground text-[0.75rem]">Modified exclusions</span>
          </div>
        )}
        {pendingList.map((item) => (
          <div key={item.rule_id} className="py-1 flex flex-col sm:flex-row sm:items-center justify-between text-[0.875rem]">
            <span className="font-mono text-foreground font-medium">{item.rule_id}</span>
            <span className="text-muted-foreground text-[0.75rem]">{item.fields.join(", ")}</span>
          </div>
        ))}
      </div>
    </div>
  );
});

interface ExclusionBadgeListProps {
  paths: string[];
  onRemove: (path: string) => void;
}

const ExclusionBadgeList = memo(function ExclusionBadgeList({ paths, onRemove }: ExclusionBadgeListProps) {
  if (paths.length === 0) {
    return <span className="text-[0.875rem] text-muted-foreground italic">No global exclusions configured.</span>;
  }
  return (
    <>
      {paths.map((p) => (
        <Badge
          key={p}
          variant="outline"
          className="flex items-center gap-1.5 px-2 py-1 bg-muted rounded text-[0.875rem] font-mono border border-border text-foreground transition-all duration-150 animate-in fade-in zoom-in-95 ease-out-quart"
        >
          {p}
          <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={() => onRemove(p)}
            className="h-4 w-4 rounded-full p-0 text-muted-foreground/60 hover:text-signal-block hover:bg-transparent"
            aria-label={`Remove path ${p}`}
          >
            <X className="w-3.5 h-3.5" />
          </Button>
        </Badge>
      ))}
    </>
  );
});

interface GlobalExclusionsPanelProps {
  paths: string[];
  draftPath: string;
  onDraftChange: (val: string) => void;
  onAdd: () => void;
  onRemove: (path: string) => void;
}

const GlobalExclusionsPanel = memo(function GlobalExclusionsPanel({
  paths,
  draftPath,
  onDraftChange,
  onAdd,
  onRemove,
}: GlobalExclusionsPanelProps) {
  return (
    <div className="p-4 border border-border rounded-md bg-card/10 space-y-3">
      <div className="flex items-center gap-2">
        <Globe className="w-4 h-4 text-muted-foreground" />
        <span className="font-medium text-[0.875rem]">Global Path Exclusions</span>
        <span className="text-[0.75rem] text-muted-foreground">
          (suppresses repo-strict/project rules; always-on safety rules still run)
        </span>
      </div>
      <div className="flex flex-wrap gap-2 min-h-[28px]">
        <ExclusionBadgeList paths={paths} onRemove={onRemove} />
      </div>
      <div className="flex gap-2 max-w-md">
        <Input
          value={draftPath}
          onChange={(e) => onDraftChange(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && onAdd()}
          placeholder="e.g., src/legacy/** or **/generated/**"
          className="h-8 text-[0.875rem] font-mono bg-background"
        />
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={onAdd}
          disabled={!draftPath.trim()}
          className="flex items-center gap-1.5 px-3 h-8 text-[0.875rem] font-medium rounded bg-primary/10 text-primary border border-primary/20 hover:bg-primary/20 disabled:opacity-40 transition-colors whitespace-nowrap"
        >
          <Plus className="w-3.5 h-3.5" /> Add Exclusion
        </Button>
      </div>
    </div>
  );
});

interface OperationalStatusPanelProps {
  totals: {
    total: number;
    hookEnabled: number;
    hookOff: number;
    cliEnabled: number;
    cliOff: number;
    activeFired: number;
    categoryCounts: Record<string, { total: number; enabled: number; fired: number }>;
  };
}

const OperationalStatusPanel = memo(function OperationalStatusPanel({ totals }: OperationalStatusPanelProps) {
  return (
    <div className="py-2.5 border-y border-border">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-[0.875rem] text-muted-foreground mb-2">
        <span className="font-semibold text-foreground">Console Status:</span>
        <span>
          Total: <strong className="text-foreground">{totals.total}</strong>
        </span>
        <span>•</span>
        <span>
          Hook: <strong className="text-signal-allow">{totals.hookEnabled} on</strong> /{" "}
          <strong className="text-muted-foreground/80">{totals.hookOff} off</strong>
        </span>
        <span>•</span>
        <span>
          CLI: <strong className="text-primary">{totals.cliEnabled} on</strong> /{" "}
          <strong className="text-muted-foreground/80">{totals.cliOff} off</strong>
        </span>
        <span>•</span>
        <span>
          Active (recently firing): <strong className="text-signal-ask">{totals.activeFired}</strong>
        </span>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-x-4 gap-y-2 text-[0.75rem] text-muted-foreground/80">
        {Object.entries(totals.categoryCounts).map(([catName, counts]) => (
          <div key={catName} className="flex items-center justify-between py-0.5 border-b border-border/20">
            <span className="truncate pr-1">{catName}</span>
            <span className="font-mono text-foreground font-medium shrink-0">
              {counts.enabled}/{counts.total} ({counts.fired} fired)
            </span>
          </div>
        ))}
      </div>
    </div>
  );
});

export function RuleCommandBand({ allRules }: RuleCommandBandProps) {
  const { config, savedConfig, pendingCount, setSkipPaths, saveConfig, discardChanges, saveStatus, saveError, apiAvailable, loading } =
    useRulesConfig();

  const [draftPath, setDraftPath] = useState("");
  const [showPendingPanel, setShowPendingPanel] = useState(false);

  const paths = useMemo(() => config.skip_paths ?? [], [config.skip_paths]);

  const addPath = useCallback(() => {
    const p = draftPath.trim();
    if (!p || paths.includes(p)) return;
    setSkipPaths([...paths, p]);
    setDraftPath("");
  }, [draftPath, paths, setSkipPaths]);

  const removePath = useCallback(
    (p: string) => {
      setSkipPaths(paths.filter((x) => x !== p));
    },
    [paths, setSkipPaths],
  );

  const totals = useMemo(() => {
    const total = allRules.length;
    const hookEnabled = allRules.filter((r) => r.hookSupported && r.hookEnabled).length;
    const hookOff = allRules.filter((r) => r.hookSupported && !r.hookEnabled).length;
    const cliEnabled = allRules.filter((r) => r.cliSupported && r.cliEnabled).length;
    const cliOff = allRules.filter((r) => r.cliSupported && !r.cliEnabled).length;
    const activeFired = allRules.filter((r) => r.enabled && r.fireCount > 0).length;

    const categoryCounts: Record<string, { total: number; enabled: number; fired: number }> = {};
    for (const r of allRules) {
      if (!categoryCounts[r.category]) {
        categoryCounts[r.category] = { total: 0, enabled: 0, fired: 0 };
      }
      categoryCounts[r.category].total++;
      if (r.enabled) {
        categoryCounts[r.category].enabled++;
      }
      if (r.fireCount > 0) {
        categoryCounts[r.category].fired++;
      }
    }

    return { total, hookEnabled, hookOff, cliEnabled, cliOff, activeFired, categoryCounts };
  }, [allRules]);

  const pendingList = useMemo(() => {
    return getPendingChangesList(savedConfig, config, allRules);
  }, [savedConfig, config, allRules]);

  const skipPathsChanged = useMemo(() => {
    const savedPaths = savedConfig.skip_paths ?? [];
    return JSON.stringify([...savedPaths].sort()) !== JSON.stringify([...paths].sort());
  }, [savedConfig.skip_paths, paths]);

  const handleTogglePendingPanel = useCallback(() => {
    setShowPendingPanel((p) => !p);
  }, []);

  if (loading) return null;

  return (
    <div className="space-y-4 font-sans text-[1rem]">
      <CommandTopBar
        apiAvailable={apiAvailable}
        pendingCount={pendingCount}
        showPendingPanel={showPendingPanel}
        onTogglePendingPanel={handleTogglePendingPanel}
        saveStatus={saveStatus}
        saveError={saveError}
        onSave={saveConfig}
        onDiscard={discardChanges}
      />
      {pendingCount > 0 && showPendingPanel && <PendingChangesPanel skipPathsChanged={skipPathsChanged} pendingList={pendingList} />}
      <GlobalExclusionsPanel paths={paths} draftPath={draftPath} onDraftChange={setDraftPath} onAdd={addPath} onRemove={removePath} />
      <OperationalStatusPanel totals={totals} />
    </div>
  );
}
