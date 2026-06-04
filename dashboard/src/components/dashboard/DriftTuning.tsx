import { useEffect, useState, type ReactNode } from "react";
import type { HarnessPlatformStatus, HarnessStatusResponse, RuntimeConfig, Severity, OperationalContext } from "@/types/slopgate";
import { cn } from "@/lib/utils";
import { XCircle, ArrowUpDown, FolderX, Flame, ShieldCheck, RadioTower, MapPin, RotateCcw, PlugZap, AlertTriangle, CheckCircle2, CircleDashed } from "lucide-react";

const SEVERITY_COLOR: Record<Severity, string> = {
  LOW: "text-severity-low",
  MEDIUM: "text-severity-medium",
  HIGH: "text-severity-high",
  CRITICAL: "text-severity-critical",
};

const API_BASE = window.location.origin + (import.meta.env.BASE_URL.replace(/\/$/, ""));
const HARNESS_ENDPOINT = `${API_BASE}/api/harness/status`;

const STATUS_CLASS: Record<HarnessPlatformStatus["status"], string> = {
  installed: "text-signal-allow bg-signal-allow/10 border-signal-allow/20",
  partial: "text-signal-ask bg-signal-ask/10 border-signal-ask/20",
  missing: "text-muted-foreground bg-muted/20 border-border",
  disabled: "text-muted-foreground bg-muted/20 border-border",
  error: "text-signal-deny bg-signal-deny/10 border-signal-deny/20",
};

function StatusIcon({ status }: { status: HarnessPlatformStatus["status"] }) {
  if (status === "installed") return <CheckCircle2 className="w-3 h-3" />;
  if (status === "partial" || status === "error") return <AlertTriangle className="w-3 h-3" />;
  return <CircleDashed className="w-3 h-3" />;
}

function compactList(values: string[], limit = 3): string {
  if (values.length === 0) return "none";
  const head = values.slice(0, limit).join(", ");
  return values.length > limit ? `${head}, +${values.length - limit}` : head;
}

interface Props {
  config: RuntimeConfig;
  hottestRepos: Array<{ repo: string; count: number }>;
  operationalContext: OperationalContext;
}

function CountList({ rows, emptyLabel = "No data" }: { rows: Array<{ label: string; count: number }>; emptyLabel?: string }) {
  if (rows.length === 0) {
    return <div className="text-[10px] text-muted-foreground px-2 py-1">{emptyLabel}</div>;
  }
  const max = Math.max(...rows.map(r => r.count), 1);
  return (
    <div className="space-y-1">
      {rows.map((row, i) => (
        <div key={row.label} className="flex items-center justify-between gap-2 px-2 py-1 rounded-sm bg-muted/20 text-xs">
          <span className="font-mono truncate" title={row.label}>{row.label}</span>
          <div className="flex items-center gap-2 shrink-0">
            <div className="w-14 h-1.5 rounded-full bg-muted overflow-hidden">
              <div
                className={cn("h-full rounded-full", i === 0 ? "bg-primary" : "bg-muted-foreground/50")}
                style={{ width: `${Math.max(8, (row.count / max) * 100)}%` }}
              />
            </div>
            <span className="text-muted-foreground w-8 text-right">{row.count}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

function OpsCard({ title, icon: Icon, children }: { title: string; icon: typeof ShieldCheck; children: ReactNode }) {
  return (
    <div className="border border-border rounded-md bg-card/30 p-3">
      <div className="flex items-center gap-2 mb-2">
        <Icon className="w-3 h-3 text-primary" />
        <h4 className="text-[10px] text-muted-foreground uppercase tracking-wider">{title}</h4>
      </div>
      {children}
    </div>
  );
}

function HarnessStatusPanel() {
  const [status, setStatus] = useState<HarnessStatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(HARNESS_ENDPOINT, { signal: AbortSignal.timeout(12000) })
      .then(async r => {
        const body = await r.json() as HarnessStatusResponse;
        if (!r.ok || body.error) throw new Error(body.error ?? `HTTP ${r.status}`);
        return body;
      })
      .then(body => {
        if (cancelled) return;
        setStatus(body);
        setError(null);
        setLoading(false);
      })
      .catch(exc => {
        if (cancelled) return;
        setError(exc instanceof Error ? exc.message : String(exc));
        setLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  const platforms = status?.platforms ?? [];

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between px-1">
        <h3 className="text-xs text-muted-foreground uppercase tracking-wider flex items-center gap-1.5">
          <PlugZap className="w-3.5 h-3.5" />
          Harness Status
        </h3>
        <div className="text-[10px] text-muted-foreground">
          read-only{status?.ssh_host ? ` · ${status.ssh_host}` : ""}
        </div>
      </div>

      <div className="border border-border rounded-md bg-card/30 p-3 space-y-2">
        {loading && <div className="text-xs text-muted-foreground">Checking installed hook harnesses…</div>}
        {error && (
          <div className="flex items-center gap-2 text-xs text-signal-deny bg-signal-deny/10 border border-signal-deny/20 rounded-md px-2 py-1.5">
            <AlertTriangle className="w-3.5 h-3.5" />
            {error}
          </div>
        )}
        {!loading && !error && platforms.length === 0 && (
          <div className="text-xs text-muted-foreground">No harness status returned.</div>
        )}
        {platforms.map(platform => (
          <div key={platform.id} className="rounded-md border border-border/70 bg-background/30 p-2 space-y-2">
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-medium">{platform.label}</span>
                  <span className="text-[10px] text-muted-foreground">{platform.capability}</span>
                </div>
                <div className="text-[10px] text-muted-foreground">{platform.support}</div>
              </div>
              <span className={cn("shrink-0 inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] uppercase", STATUS_CLASS[platform.status])}>
                <StatusIcon status={platform.status} />
                {platform.status}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-2 text-[10px] text-muted-foreground">
              <div>
                <span className="uppercase tracking-wider">config</span>
                <div className="font-mono text-foreground truncate" title={platform.config_path}>{platform.config_path}</div>
              </div>
              <div>
                <span className="uppercase tracking-wider">dry-run install</span>
                <div className={cn("font-mono", platform.dry_run.ok ? "text-signal-allow" : "text-signal-ask")}>
                  {platform.dry_run.available ? (platform.dry_run.ok ? "ok" : platform.dry_run.note ?? `exit ${platform.dry_run.returncode ?? "?"}`) : "unavailable"}
                </div>
              </div>
              <div>
                <span className="uppercase tracking-wider">events</span>
                <div className="font-mono text-foreground">
                  {platform.configured_events.length}/{platform.expected_events.length} configured
                </div>
              </div>
              <div>
                <span className="uppercase tracking-wider">commands</span>
                <div className={cn("font-mono", platform.all_commands_reference_slopgate ? "text-signal-allow" : "text-signal-ask")}>
                  {platform.slopgate_command_count} slopgate handle
                </div>
              </div>
            </div>

            {platform.feature_flag_path && (
              <div className="text-[10px] text-muted-foreground">
                feature flag <span className="font-mono">{platform.feature_flag_path}</span>: {platform.feature_flag_enabled ? "enabled" : "missing/off"}
              </div>
            )}
            {platform.missing_events.length > 0 && (
              <div className="text-[10px] text-signal-ask">
                missing events: {compactList(platform.missing_events)}
              </div>
            )}
            {platform.disabled_plugin_present && !platform.config_exists && (
              <div className="text-[10px] text-signal-ask">disabled plugin copy exists outside the auto-loaded plugin directory.</div>
            )}
            {platform.error && <div className="text-[10px] text-signal-deny">{platform.error}</div>}
          </div>
        ))}
      </div>
    </div>
  );
}

export function DriftTuning({ config, hottestRepos, operationalContext }: Props) {
  return (
    <div className="space-y-4">
      <h3 className="text-xs text-muted-foreground uppercase tracking-wider px-1">Drift & Tuning</h3>

      <div className="grid grid-cols-2 gap-3">
        {/* Disabled rules */}
        <div className="border border-border rounded-md bg-card/30 p-3">
          <div className="flex items-center gap-2 mb-2">
            <XCircle className="w-3 h-3 text-signal-deny" />
            <h4 className="text-[10px] text-muted-foreground uppercase tracking-wider">Disabled Rules</h4>
          </div>
          <div className="space-y-1">
            {config.disabled_rules.map(r => (
              <div key={r.rule_id} className="flex items-center justify-between px-2 py-1 rounded-sm bg-muted/20 text-xs">
                <span className="font-mono">{r.rule_id}</span>
                <span className="text-[10px] text-muted-foreground">{r.disabled_date}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Severity overrides */}
        <div className="border border-border rounded-md bg-card/30 p-3">
          <div className="flex items-center gap-2 mb-2">
            <ArrowUpDown className="w-3 h-3 text-signal-ask" />
            <h4 className="text-[10px] text-muted-foreground uppercase tracking-wider">Severity Overrides</h4>
          </div>
          <div className="space-y-1">
            {config.severity_overrides.map(o => (
              <div key={o.rule_id} className="flex items-center justify-between px-2 py-1 rounded-sm bg-muted/20 text-xs">
                <span className="font-mono truncate">{o.rule_id}</span>
                <div className="flex items-center gap-1 shrink-0">
                  <span className={cn("text-[10px]", SEVERITY_COLOR[o.original])}>{o.original}</span>
                  <span className="text-muted-foreground">→</span>
                  <span className={cn("text-[10px] font-semibold", SEVERITY_COLOR[o.override])}>{o.override}</span>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Skipped repos */}
        <div className="border border-border rounded-md bg-card/30 p-3">
          <div className="flex items-center gap-2 mb-2">
            <FolderX className="w-3 h-3 text-muted-foreground" />
            <h4 className="text-[10px] text-muted-foreground uppercase tracking-wider">Skipped Repos</h4>
          </div>
          <div className="space-y-1">
            {config.skip_repos.map(r => (
              <div key={r} className="px-2 py-1 rounded-sm bg-muted/20 text-xs font-mono">{r}</div>
            ))}
            <div className="text-[10px] text-muted-foreground mt-1">
              + {config.skip_paths.length} skip paths configured
            </div>
          </div>
        </div>

        {/* Hottest repos */}
        <div className="border border-border rounded-md bg-card/30 p-3">
          <div className="flex items-center gap-2 mb-2">
            <Flame className="w-3 h-3 text-signal-ask" />
            <h4 className="text-[10px] text-muted-foreground uppercase tracking-wider">Hottest Repos</h4>
          </div>
          <div className="space-y-1">
            {hottestRepos.slice(0, 6).map((r, i) => (
              <div key={r.repo} className="flex items-center justify-between px-2 py-1 rounded-sm bg-muted/20 text-xs">
                <span className="font-mono">{r.repo}</span>
                <div className="flex items-center gap-2">
                  <div className="w-16 h-1.5 rounded-full bg-muted overflow-hidden">
                    <div
                      className={cn("h-full rounded-full", i === 0 ? "bg-signal-ask" : "bg-primary")}
                      style={{ width: `${(r.count / hottestRepos[0].count) * 100}%` }}
                    />
                  </div>
                  <span className="text-muted-foreground w-8 text-right">{r.count}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      <HarnessStatusPanel />

      <div className="space-y-2">
        <h3 className="text-xs text-muted-foreground uppercase tracking-wider px-1">Operational Context</h3>
        <div className="grid grid-cols-2 gap-3">
          <OpsCard title="Platform Capability" icon={RadioTower}>
            <CountList rows={operationalContext.platformCapabilities} emptyLabel="No platform metadata" />
            {operationalContext.degradedReasons.length > 0 && (
              <div className="mt-2 pt-2 border-t border-border/50">
                <div className="text-[10px] text-muted-foreground mb-1">Top degraded reasons</div>
                <CountList rows={operationalContext.degradedReasons} />
              </div>
            )}
          </OpsCard>

          <OpsCard title="Enforcement Modes" icon={ShieldCheck}>
            <CountList rows={operationalContext.enforcementModes} emptyLabel="No enforcement metadata" />
          </OpsCard>

          <OpsCard title="Resolved Repo Roots" icon={MapPin}>
            <CountList rows={operationalContext.repoRoots} emptyLabel="No repo root metadata" />
            {operationalContext.pathlessResults > 0 && (
              <div className="text-[10px] text-signal-ask mt-2">
                {operationalContext.pathlessResults} result{operationalContext.pathlessResults === 1 ? "" : "s"} had no candidate paths in this window.
              </div>
            )}
          </OpsCard>

          <OpsCard title="Deny Recovery" icon={RotateCcw}>
            <div className="px-2 py-1 rounded-sm bg-muted/20 text-xs flex items-center justify-between">
              <span className="text-muted-foreground">resolution rate</span>
              <span className="font-mono">
                {operationalContext.resolutionRate === null ? "n/a" : `${operationalContext.resolutionRate.toFixed(1)}%`}
              </span>
            </div>
            <div className="text-[10px] text-muted-foreground mt-1 px-2">
              {operationalContext.resolvedBlockedSessions}/{operationalContext.blockedSessions} blocked sessions later produced allow/context/warn/info.
            </div>
            {operationalContext.repeatedDenials.length > 0 && (
              <div className="mt-2 pt-2 border-t border-border/50">
                <div className="text-[10px] text-muted-foreground mb-1">Repeated deny loops</div>
                <CountList rows={operationalContext.repeatedDenials} />
              </div>
            )}
          </OpsCard>
        </div>
      </div>
    </div>
  );
}
