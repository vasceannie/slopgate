import { cn } from "@/lib/utils";
import { Shield, XCircle, HelpCircle, SkipForward, AlertOctagon, AlertTriangle } from "lucide-react";
import { Sparkline } from "./Sparkline";

interface PostureData {
  totalInvocations: number;
  blockRate: number;
  denyRate: number;
  askRate: number;
  skippedCount: number;
  errorCount: number;
  decisionCounts: Record<string, number>;
  sparklines: {
    invocations: number[];
    blockRate: number[];
    denyRate: number[];
    askRate: number[];
    skipped: number[];
    errors: number[];
  };
}

interface SourceStatusData {
  warning: string | null;
  meta: {
    latestDataAt: string | null;
    totalRecords: number;
    acceptedStreamRecords: number;
    rejectedStreamRecords: number;
  };
}

interface Props {
  data: PostureData;
  sourceStatus?: SourceStatusData;
}

function KpiCard({ label, value, icon: Icon, color, subValue, sparkData, sparkColor }: {
  label: string; value: string; icon: React.ElementType; color: string;
  subValue?: string; sparkData?: number[]; sparkColor?: string;
}) {
  return (
    <div className={cn("flex items-center gap-3 px-4 py-3 rounded-md border border-border bg-card", color)}>
      <Icon className="w-4 h-4 shrink-0" />
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <div className="text-lg font-semibold leading-tight">{value}</div>
          {sparkData && sparkData.length > 1 && (
            <Sparkline data={sparkData} color={sparkColor || "hsl(142, 50%, 45%)"} width={48} height={16} />
          )}
        </div>
        <div className="text-[10px] text-muted-foreground uppercase tracking-wider">{label}</div>
        {subValue && <div className="text-[10px] text-muted-foreground">{subValue}</div>}
      </div>
    </div>
  );
}

export function PostureStrip({ data, sourceStatus }: Props) {
  const sp = data.sparklines ?? { invocations: [], blockRate: [], denyRate: [], askRate: [], skipped: [], errors: [] };
  return (
    <div className="space-y-3">
      {sourceStatus?.warning && (
        <div className="flex flex-wrap items-center gap-2 rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
          <AlertTriangle className="w-3.5 h-3.5 shrink-0 text-amber-300" />
          <span>{sourceStatus.warning}</span>
          <span className="text-amber-200/70">
            accepted {sourceStatus.meta.totalRecords.toLocaleString()} records · dataset latest {sourceStatus.meta.latestDataAt ?? "unknown"}
          </span>
        </div>
      )}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
      <KpiCard
        label="Invocations"
        value={data.totalInvocations.toLocaleString()}
        icon={Shield}
        color="glow-green"
        sparkData={sp.invocations}
        sparkColor="hsl(142, 50%, 45%)"
      />
      <KpiCard
        label="Block Rate"
        value={`${data.blockRate.toFixed(1)}%`}
        icon={XCircle}
        color={data.blockRate > 5 ? "glow-red" : ""}
        subValue={`${data.decisionCounts.block || 0} blocked`}
        sparkData={sp.blockRate}
        sparkColor="hsl(0, 85%, 60%)"
      />
      <KpiCard
        label="Deny Rate"
        value={`${data.denyRate.toFixed(1)}%`}
        icon={XCircle}
        color={data.denyRate > 10 ? "glow-red" : ""}
        subValue={`${data.decisionCounts.deny || 0} denied`}
        sparkData={sp.denyRate}
        sparkColor="hsl(0, 72%, 51%)"
      />
      <KpiCard
        label="Ask Rate"
        value={`${data.askRate.toFixed(1)}%`}
        icon={HelpCircle}
        color={data.askRate > 20 ? "glow-amber" : ""}
        subValue={`${data.decisionCounts.ask || 0} asked`}
        sparkData={sp.askRate}
        sparkColor="hsl(38, 92%, 50%)"
      />
      <KpiCard
        label="Skipped"
        value={data.skippedCount.toString()}
        icon={SkipForward}
        color=""
        sparkData={sp.skipped}
        sparkColor="hsl(215, 12%, 50%)"
      />
      <KpiCard
        label="Errors"
        value={data.errorCount.toString()}
        icon={AlertOctagon}
        color={data.errorCount > 0 ? "glow-red" : ""}
        sparkData={sp.errors}
        sparkColor="hsl(300, 70%, 55%)"
      />
      </div>
    </div>
  );
}
