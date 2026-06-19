import { Activity, AlertTriangle, Check, Copy, RefreshCw, Settings, ShieldAlert, ShieldCheck, Terminal } from "lucide-react";
import { useState } from "react";
import type { HarnessStatusState } from "@/hooks/useHarnessStatus";
import { cn } from "@/lib/utils";
import type { HarnessPlatformStatus, RuntimeConfig } from "@/types/slopgate";

interface OpsPostureStripProps {
  asyncFailCount: number;
  config: RuntimeConfig;
  harnessStatus: HarnessStatusState;
}

export function OpsPostureStrip({ asyncFailCount, config, harnessStatus }: OpsPostureStripProps) {
  const { status, loading, error } = harnessStatus;

  const disabledRulesCount = config.disabled_rules.length;
  const severityOverridesCount = config.severity_overrides.length;

  const platforms = status?.platforms ?? [];
  const hasHarnessData = platforms.length > 0;
  const installedPlatforms = platforms.filter((p) => p.status === "installed");
  const errorPlatforms = platforms.filter((p) => p.status === "error");
  const partialPlatforms = platforms.filter((p) => p.status === "partial" || p.status === "disabled" || p.status === "missing");

  let posture: "Checking" | "Quiet" | "Degraded" | "Action Needed" = loading ? "Checking" : "Quiet";
  let statusMessage = "All systems operational. No action required.";
  let debugCommand = "slopgate test";
  let debugNote = "Run self-tests to verify your local installation.";

  if (loading) {
    statusMessage = "Checking harness health against the live API.";
    debugNote = "Status will update when the harness scan returns.";
  } else if (asyncFailCount > 0 || errorPlatforms.length > 0 || error) {
    posture = "Degraded";
    if (asyncFailCount > 0 && (errorPlatforms.length > 0 || error)) {
      statusMessage = `${asyncFailCount} active async failures & platform harness error(s).`;
      debugCommand = "slopgate test && slopgate install all";
      debugNote = "Verify execution flow logs and reinstall platform hooks.";
    } else if (asyncFailCount > 0) {
      statusMessage = `${asyncFailCount} active async failures detected.`;
      debugCommand = "slopgate test";
      debugNote = "Verify execution flow logs and linter diagnostics.";
    } else {
      statusMessage = error ? `Failed to load harness status: ${error}` : `${errorPlatforms.length} platform harness error(s) detected.`;
      debugCommand = "slopgate install all";
      debugNote = "Reinstall or check configuration files for platform hooks.";
    }
  } else if (!hasHarnessData) {
    posture = "Action Needed";
    statusMessage = "Harness status returned no platform records.";
    debugCommand = "slopgate install all";
    debugNote = "Run hook installer to detect local platform integrations.";
  } else if (partialPlatforms.length > 0 || disabledRulesCount > 0 || severityOverridesCount > 0) {
    posture = "Action Needed";
    if (partialPlatforms.length > 0) {
      const partialReason = describePartialPlatform(partialPlatforms[0]);
      statusMessage = partialReason.message;
      debugCommand = partialReason.command;
      debugNote = partialReason.note;
    } else if (disabledRulesCount > 0 || severityOverridesCount > 0) {
      statusMessage = `${disabledRulesCount} disabled rules and ${severityOverridesCount} severity overrides active.`;
      debugCommand = "slopgate config show";
      debugNote = "Review active configurations and severity overrides.";
    }
  }

  const harnessSummary = loading ? "..." : hasHarnessData ? `${installedPlatforms.length}/${platforms.length}` : "—";

  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    navigator.clipboard.writeText(debugCommand);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="mb-6 rounded-lg border border-border bg-card/45 p-5 shadow-sm">
      <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between w-full">
        {/* Left: Posture Indicator & Message */}
        <div className="flex items-start gap-4 min-w-0 flex-1">
          <div
            className={cn(
              "p-3 rounded-lg border shrink-0",
              posture === "Checking" && "bg-muted/20 border-border text-muted-foreground",
              posture === "Quiet" && "bg-signal-allow/10 border-signal-allow/20 text-signal-allow glow-green",
              posture === "Action Needed" && "bg-signal-ask/10 border-signal-ask/20 text-signal-ask glow-amber",
              posture === "Degraded" && "bg-signal-deny/10 border-signal-deny/20 text-signal-deny glow-red",
            )}
          >
            {posture === "Checking" && <RefreshCw className="w-6 h-6 animate-spin" />}
            {posture === "Quiet" && <ShieldCheck className="w-6 h-6" />}
            {posture === "Action Needed" && <AlertTriangle className="w-6 h-6" />}
            {posture === "Degraded" && <ShieldAlert className="w-6 h-6" />}
          </div>
          <div className="space-y-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-base font-bold tracking-tight text-foreground">Ops posture: {posture}</span>
              {loading && <RefreshCw className="w-4 h-4 animate-spin text-muted-foreground" />}
            </div>
            <p className="text-sm font-medium text-foreground/90 leading-normal">{statusMessage}</p>
          </div>
        </div>

        {/* Middle: 3 Decisive Facts */}
        <div className="flex flex-wrap items-center gap-x-8 gap-y-3 py-3 border-y border-border lg:border-y-0 lg:border-x lg:px-8 lg:py-0 shrink-0">
          <div className="flex flex-col gap-0.5">
            <span className="text-[11px] text-muted-foreground uppercase tracking-wider font-semibold">Async Failures:</span>
            <div className="flex items-center gap-1.5">
              <Terminal className="w-4 h-4 text-muted-foreground" />
              <span className={cn("text-base font-mono font-bold", asyncFailCount > 0 ? "text-signal-deny" : "text-foreground")}>
                {asyncFailCount}
              </span>
            </div>
          </div>

          <div className="flex flex-col gap-0.5">
            <span className="text-[11px] text-muted-foreground uppercase tracking-wider font-semibold">Local rule changes:</span>
            <div className="flex items-center gap-2">
              <Settings className="w-4 h-4 text-muted-foreground" />
              <span className="text-base font-mono font-bold text-foreground">{disabledRulesCount + severityOverridesCount}</span>
              <span className="text-[10px] text-muted-foreground/80 font-medium">
                ({disabledRulesCount} disabled, {severityOverridesCount} overrides)
              </span>
            </div>
          </div>

          <div className="flex flex-col gap-0.5">
            <span className="text-[11px] text-muted-foreground uppercase tracking-wider font-semibold">Harnesses:</span>
            <div className="flex items-center gap-1.5">
              <Activity className="w-4 h-4 text-muted-foreground" />
              <span className="text-base font-mono font-bold text-foreground">{harnessSummary}</span>
              {!loading && !hasHarnessData && <span className="text-[10px] text-muted-foreground font-medium">(unavailable)</span>}
              {errorPlatforms.length > 0 && <span className="text-[10px] text-signal-deny font-medium">({errorPlatforms.length} err)</span>}
            </div>
          </div>
        </div>

        {/* Right: Suggested next action */}
        <div className="flex flex-col gap-1.5 lg:max-w-xs xl:max-w-md w-full lg:w-auto shrink-0">
          <span className="text-[11px] text-muted-foreground uppercase tracking-wider font-semibold">Suggested next action</span>
          <div className="flex items-center justify-between gap-3 bg-muted/40 border border-border/80 rounded px-3 py-2 font-mono text-xs text-foreground group relative">
            <div className="flex items-center gap-1.5 min-w-0 flex-1">
              <span className="text-primary shrink-0">$</span>
              <span className="break-all select-all font-medium text-foreground">{debugCommand}</span>
            </div>
            <button
              type="button"
              onClick={handleCopy}
              className="p-1 rounded hover:bg-muted/80 text-muted-foreground hover:text-foreground transition-colors shrink-0"
              title="Copy command"
            >
              {copied ? <Check className="w-4 h-4 text-signal-allow" /> : <Copy className="w-4 h-4" />}
            </button>
          </div>
          <span className="text-[10px] text-muted-foreground italic leading-normal">{debugNote}</span>
        </div>
      </div>
    </div>
  );
}

function describePartialPlatform(platform: HarnessPlatformStatus): {
  message: string;
  command: string;
  note: string;
} {
  if (platform.feature_flag_path && !platform.feature_flag_enabled) {
    return {
      message: `${platform.label} hook entries are present, but Codex hooks are disabled in config.toml.`,
      command: "slopgate install codex",
      note: "Installer should set [features] hooks = true; if it already did, refresh harness status.",
    };
  }

  if (platform.missing_events.length > 0) {
    return {
      message: `${platform.label} is missing ${platform.missing_events.length} hook event${platform.missing_events.length === 1 ? "" : "s"}.`,
      command: `slopgate install ${platform.id}`,
      note: "Installer should add the missing event entries to the platform hook file.",
    };
  }

  if (!platform.all_commands_reference_slopgate) {
    return {
      message: `${platform.label} has hook commands that do not all call slopgate.`,
      command: `slopgate install ${platform.id}`,
      note: "Review the hook file for stale or non-Slopgate command entries.",
    };
  }

  return {
    message: `${platform.label} returned a partial harness state; inspect the harness row for the exact missing field.`,
    command: `slopgate install ${platform.id}`,
    note: "Use the detailed harness status section below before reinstalling repeatedly.",
  };
}
