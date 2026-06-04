import { ResponsiveBar } from "@nivo/bar";
import { ResponsivePie } from "@nivo/pie";
import { useState, useEffect } from "react";
import type { Decision, Severity } from "@/types/slopgate";
import { cn } from "@/lib/utils";
import { SEVERITY_COLORS, NIVO_DARK_THEME } from "@/lib/chartTheme";
import { getRuleDescription } from "@/lib/ruleDescriptions";

interface RuleEntry {
  rule_id: string;
  count: number;
  severity: Severity;
  decisions: Record<string, number>;
}

interface Props {
  topRules: RuleEntry[];
  duplicationByRule: Array<{ rule_id: string; count: number }>;
}

type View = "firing" | "blocking" | "warning";

const BAR_PAGE_SIZE = 12;
export const DEFAULT_TOP_RULE_VIEW: View = "blocking";

export function TopRules({ topRules, duplicationByRule }: Props) {
  const [view, setView] = useState<View>(DEFAULT_TOP_RULE_VIEW);
  const [barPage, setBarPage] = useState(0);

  // Reset page when view changes
  useEffect(() => setBarPage(0), [view]);

  const filtered = view === "blocking"
    ? topRules.filter(r => (r.decisions.block || 0) + (r.decisions.deny || 0) > 0)
      .sort((a, b) => ((b.decisions.block || 0) + (b.decisions.deny || 0)) - ((a.decisions.block || 0) + (a.decisions.deny || 0)))
    : view === "warning"
    ? topRules.filter(r => (r.decisions.warn || 0) + (r.decisions.context || 0) > 0)
      .sort((a, b) => ((b.decisions.warn || 0) + (b.decisions.context || 0)) - ((a.decisions.warn || 0) + (a.decisions.context || 0)))
    : topRules;

  const barPageCount = Math.max(1, Math.ceil(filtered.length / BAR_PAGE_SIZE));
  const barData = filtered.slice(barPage * BAR_PAGE_SIZE, (barPage + 1) * BAR_PAGE_SIZE).map(r => ({
    rule: r.rule_id.length > 24 ? r.rule_id.slice(0, 22) + "…" : r.rule_id,
    count: r.count,
    color: SEVERITY_COLORS[r.severity],
  }));

  const severityCounts = topRules.reduce((acc, r) => {
    acc[r.severity] = (acc[r.severity] || 0) + r.count;
    return acc;
  }, {} as Record<Severity, number>);

  const severityLabels: Record<Severity, string> = { LOW: "Low", MEDIUM: "Med", HIGH: "High", CRITICAL: "Crit" };
  const pieData = (["LOW", "MEDIUM", "HIGH", "CRITICAL"] as Severity[]).map(s => ({
    id: s, label: severityLabels[s], value: severityCounts[s] || 0, color: SEVERITY_COLORS[s],
  }));

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-xs text-muted-foreground uppercase tracking-wider px-1">Top Pressure Rules</h3>
        <div className="flex gap-1">
          {(["firing", "blocking", "warning"] as View[]).map(v => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={cn(
                "px-2 py-0.5 text-[10px] rounded-sm transition-colors uppercase",
                view === v ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted"
              )}
            >
              {v}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-5 gap-3">
        <div className="col-span-3 border border-border rounded-md bg-card/30 p-2 flex flex-col gap-1">
          <div className="h-[260px]">
          <ResponsiveBar
            data={barData}
            keys={["count"]}
            indexBy="rule"
            layout="horizontal"
            margin={{ top: 5, right: 30, bottom: 5, left: 160 }}
            padding={0.3}
            colors={({ data }) => (data as any).color}
            borderWidth={0}
            enableLabel={true}
            labelTextColor="hsl(210, 20%, 95%)"
            enableGridY={false}
            axisLeft={{ tickSize: 0, tickPadding: 8 }}
            axisBottom={null}
            tooltip={({ data }) => {
              const fullId = filtered.find(r => {
                const truncated = r.rule_id.length > 24 ? r.rule_id.slice(0, 22) + "…" : r.rule_id;
                return truncated === data.rule;
              })?.rule_id || String(data.rule);
              const desc = getRuleDescription(fullId);
              return (
                <div className="bg-card border border-border rounded px-3 py-2 text-xs font-mono shadow-lg">
                  <div className="font-semibold">{fullId}</div>
                  {desc && <div className="text-muted-foreground font-sans mt-0.5">{desc}</div>}
                  <div className="text-muted-foreground mt-1">Count: {data.count as number}</div>
                </div>
              );
            }}
            theme={NIVO_DARK_THEME}
          />
          </div>
          {barPageCount > 1 && (
            <div className="flex items-center justify-between text-[10px] text-muted-foreground px-1">
              <span>{filtered.length} rules</span>
              <div className="flex gap-2">
                <button disabled={barPage === 0} onClick={() => setBarPage(p => p - 1)} className="hover:text-foreground disabled:opacity-30">←</button>
                <span>{barPage + 1}/{barPageCount}</span>
                <button disabled={barPage + 1 >= barPageCount} onClick={() => setBarPage(p => p + 1)} className="hover:text-foreground disabled:opacity-30">→</button>
              </div>
            </div>
          )}
        </div>

        <div className="col-span-2 h-[280px] border border-border rounded-md bg-card/30 p-2">
          <h4 className="text-[10px] text-muted-foreground uppercase mb-1 text-center">Severity Mix</h4>
          <ResponsivePie
            data={pieData}
            margin={{ top: 5, right: 70, bottom: 10, left: 5 }}
            innerRadius={0.55}
            padAngle={2}
            cornerRadius={3}
            colors={({ data }) => data.color}
            borderWidth={1}
            borderColor="hsl(220, 15%, 15%)"
            enableArcLinkLabels={false}
            arcLabelsTextColor="hsl(210, 20%, 95%)"
            arcLabelsSkipAngle={20}
            legends={[{
              anchor: "right", direction: "column", translateX: 65,
              itemWidth: 55, itemHeight: 18, itemTextColor: "hsl(215, 12%, 50%)",
              symbolSize: 8, symbolShape: "circle",
            }]}
            theme={NIVO_DARK_THEME}
          />
        </div>
      </div>

      {/* Duplication lens — hidden when all zeros */}
      {duplicationByRule.some(d => d.count > 0) && (
        <div className="border border-border rounded-md bg-card/30 p-3">
          <h4 className="text-[10px] text-muted-foreground uppercase tracking-wider mb-2">Duplication Family</h4>
          <div className="flex flex-wrap gap-3">
            {duplicationByRule.map(d => (
              <div key={d.rule_id} className="flex items-center gap-2 px-3 py-2 rounded-sm bg-muted/30 border border-border">
                <span className="text-xs whitespace-nowrap">{d.rule_id}</span>
                <span className={cn(
                  "text-sm font-semibold ml-2",
                  d.count > 20 ? "text-signal-ask" : d.count > 5 ? "text-foreground" : "text-muted-foreground"
                )}>
                  {d.count}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}