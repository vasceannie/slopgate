import { useMemo, useState } from "react";
import { Bar, Cell, ComposedChart, LabelList, Legend, Line, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { SEVERITY_COLORS } from "@/lib/chartTheme";
import { getRuleDescription } from "@/lib/ruleDescriptions";
import { cn } from "@/lib/utils";
import type { Severity } from "@/types/slopgate";

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

interface ParetoDatum {
  rule: string;
  count: number;
  logCount: number;
  color: string;
  cumulativePct: number;
  fullId: string;
}

interface SeverityRingDatum {
  id: string;
  name: string;
  value: number;
  color: string;
  severity: Severity;
  fullId?: string;
  description?: string;
}

const MAX_PARETO_ITEMS = 12;
export const DEFAULT_TOP_RULE_VIEW: View = "blocking";

const LABEL_STYLE = {
  fontSize: 9,
  fontFamily: "JetBrains Mono",
  fill: "hsl(215, 12%, 50%)",
};

const LEGEND_WRAPPER: React.CSSProperties = {
  fontSize: 9,
  fontFamily: "JetBrains Mono",
  paddingTop: 4,
};

const SEVERITY_INNER_RING_INNER_RADIUS = 62;
const SEVERITY_INNER_RING_OUTER_RADIUS = 84;
const SEVERITY_OUTER_RING_INNER_RADIUS = 92;
const SEVERITY_OUTER_RING_OUTER_RADIUS = 118;
const SEVERITIES: Severity[] = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];
const SEVERITY_LABELS: Record<Severity, string> = {
  LOW: "Low",
  MEDIUM: "Med",
  HIGH: "High",
  CRITICAL: "Crit",
};
const SECONDARY_LEGEND_DESCRIPTION_LIMIT = 42;

function truncateDescription(description: string) {
  return description.length > SECONDARY_LEGEND_DESCRIPTION_LIMIT
    ? `${description.slice(0, SECONDARY_LEGEND_DESCRIPTION_LIMIT - 1)}…`
    : description;
}

export function TopRules({ topRules, duplicationByRule }: Props) {
  const [view, setView] = useState<View>(DEFAULT_TOP_RULE_VIEW);

  const filtered =
    view === "blocking"
      ? topRules
          .filter((r) => (r.decisions.block || 0) + (r.decisions.deny || 0) > 0)
          .sort((a, b) => (b.decisions.block || 0) + (b.decisions.deny || 0) - ((a.decisions.block || 0) + (a.decisions.deny || 0)))
      : view === "warning"
        ? topRules
            .filter((r) => (r.decisions.warn || 0) + (r.decisions.context || 0) > 0)
            .sort((a, b) => (b.decisions.warn || 0) + (b.decisions.context || 0) - ((a.decisions.warn || 0) + (a.decisions.context || 0)))
        : topRules;

  const paretoData: ParetoDatum[] = useMemo(() => {
    const visible = filtered.slice(0, MAX_PARETO_ITEMS);
    const other = filtered.slice(MAX_PARETO_ITEMS);

    const items: ParetoDatum[] = visible.map((r) => ({
      rule: r.rule_id.length > 28 ? `${r.rule_id.slice(0, 26)}…` : r.rule_id,
      count: r.count,
      logCount: Math.log10(Math.max(r.count, 1)),
      color: SEVERITY_COLORS[r.severity],
      cumulativePct: 0,
      fullId: r.rule_id,
    }));

    if (other.length > 0) {
      const otherSum = other.reduce((sum, r) => sum + r.count, 0);
      items.push({
        rule: `+${other.length} more`,
        count: otherSum,
        logCount: Math.log10(Math.max(otherSum, 1)),
        color: "hsl(215, 12%, 35%)",
        cumulativePct: 0,
        fullId: "",
      });
    }

    const total = items.reduce((sum, d) => sum + d.count, 0) || 1;
    let running = 0;
    return items.map((d) => {
      running += d.count;
      return { ...d, cumulativePct: Math.round((running / total) * 100) };
    });
  }, [filtered]);

  const severityBreakdown = useMemo(() => {
    const innerRing: SeverityRingDatum[] = SEVERITIES.map((s) => {
      const total = topRules.filter((r) => r.severity === s).reduce((sum, r) => sum + r.count, 0);
      return {
        id: s,
        name: SEVERITY_LABELS[s],
        value: total,
        color: SEVERITY_COLORS[s],
        severity: s,
      };
    }).filter((d) => d.value > 0);

    const outerRing: SeverityRingDatum[] = SEVERITIES.flatMap((s) => {
      const sorted = topRules
        .filter((r) => r.severity === s)
        .sort((a, b) => b.count - a.count)
        .slice(0, 3);
      return sorted.map((r, _i) => ({
        id: `${s}-${r.rule_id}`,
        name: r.rule_id,
        value: r.count,
        color: SEVERITY_COLORS[s],
        severity: s,
        fullId: r.rule_id,
        description: truncateDescription(getRuleDescription(r.rule_id) ?? r.rule_id),
      }));
    });

    return { innerRing, outerRing };
  }, [topRules]);

  return (
    <div className="space-y-3">
      <div className="flex min-h-[590px] flex-col gap-3 lg:h-[650px]">
        <div className="flex items-center justify-between">
          <h3 className="text-xs text-muted-foreground uppercase tracking-wider px-1">Top Pressure Rules</h3>
          <div className="flex gap-1">
            {(["firing", "blocking", "warning"] as View[]).map((v) => (
              <button
                type="button"
                key={v}
                onClick={() => setView(v)}
                className={cn(
                  "px-2 py-0.5 text-[10px] rounded-sm transition-colors uppercase",
                  view === v ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted",
                )}
              >
                {v}
              </button>
            ))}
          </div>
        </div>

        <div className="grid min-h-0 flex-1 grid-rows-[minmax(245px,0.43fr)_minmax(320px,0.57fr)] gap-4">
          <div className="flex min-h-0 flex-col gap-1 rounded-md border border-border bg-card/30 p-2">
            <div className="min-h-[215px] flex-1">
              {paretoData.length > 0 ? (
                <ResponsiveContainer width="100%" height="100%">
                  <ComposedChart data={paretoData} layout="vertical" margin={{ top: 5, right: 50, bottom: 5, left: 4 }}>
                    <XAxis
                      type="number"
                      domain={[0, "dataMax"]}
                      ticks={[0, 1, 2, 3]}
                      tickFormatter={(v) => {
                        if (v <= 0) return "0";
                        const n = Math.round(10 ** v);
                        return n >= 1000 ? `${(n / 1000).toFixed(0)}K` : String(n);
                      }}
                      tick={{
                        fontSize: 9,
                        fontFamily: "JetBrains Mono",
                        fill: "hsl(215, 12%, 50%)",
                      }}
                      axisLine={{ stroke: "hsl(220, 15%, 15%)" }}
                      tickLine={false}
                    />
                    <XAxis
                      xAxisId="pct"
                      type="number"
                      orientation="top"
                      domain={[0, 100]}
                      tickFormatter={(v) => `${v}%`}
                      tick={{
                        fontSize: 8,
                        fontFamily: "JetBrains Mono",
                        fill: "hsl(var(--signal-allow))",
                      }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <YAxis
                      type="category"
                      dataKey="rule"
                      interval={0}
                      tick={{
                        fontSize: 9,
                        fontFamily: "JetBrains Mono",
                        fill: "hsl(215, 12%, 50%)",
                      }}
                      axisLine={false}
                      tickLine={false}
                      width={170}
                    />
                    <Tooltip
                      content={({ active, payload }) => {
                        if (!active || !payload?.length) return null;
                        const d = payload[0]?.payload as ParetoDatum | undefined;
                        if (!d) return null;
                        const desc = d.fullId ? getRuleDescription(d.fullId) : null;
                        return (
                          <div className="bg-card border border-border rounded px-3 py-2 text-xs font-mono shadow-lg">
                            <div className="font-semibold">{d.fullId || d.rule}</div>
                            {desc && <div className="text-muted-foreground font-sans mt-0.5">{desc}</div>}
                            <div className="text-muted-foreground mt-1">Count: {d.count.toLocaleString()}</div>
                            <div className="text-signal-allow mt-0.5">Cumulative: {d.cumulativePct}%</div>
                          </div>
                        );
                      }}
                      cursor={{ fill: "hsl(220, 16%, 10%)" }}
                    />
                    <Bar dataKey="logCount" isAnimationActive={false} barSize={4} radius={0}>
                      {paretoData.map((entry) => (
                        <Cell key={entry.rule} fill={entry.color} />
                      ))}
                      <LabelList
                        dataKey="count"
                        position="right"
                        formatter={(v: number) => v.toLocaleString()}
                        style={LABEL_STYLE}
                        offset={6}
                      />
                    </Bar>
                    <Line
                      type="monotone"
                      xAxisId="pct"
                      dataKey="cumulativePct"
                      stroke="hsl(var(--signal-allow))"
                      strokeWidth={2}
                      strokeDasharray="4 3"
                      dot={false}
                      strokeOpacity={0.7}
                    />
                  </ComposedChart>
                </ResponsiveContainer>
              ) : (
                <div className="flex items-center justify-center h-full text-muted-foreground text-xs">
                  No rules with decisions in this view
                </div>
              )}
            </div>
            <div className="flex items-center justify-between text-[10px] text-muted-foreground px-1">
              <span>
                {filtered.length} rules
                {filtered.length > MAX_PARETO_ITEMS && ` · top ${MAX_PARETO_ITEMS} shown`}
              </span>
              <span className="text-signal-allow/70">— cumulative %</span>
            </div>
          </div>

          <div className="min-h-[320px] rounded-md border border-border bg-card/30 p-2">
            <h4 className="text-[10px] text-muted-foreground uppercase mb-1 text-center">Severity Mix</h4>
            {severityBreakdown.innerRing.length > 0 ? (
              <div className="grid h-[calc(100%-1rem)] min-h-[292px] grid-cols-[minmax(0,1fr)_220px] gap-3 -mt-1">
                <div className="min-w-0 h-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie
                        data={severityBreakdown.outerRing}
                        dataKey="value"
                        nameKey="name"
                        cx="50%"
                        cy="50%"
                        innerRadius={SEVERITY_OUTER_RING_INNER_RADIUS}
                        outerRadius={SEVERITY_OUTER_RING_OUTER_RADIUS}
                        paddingAngle={1}
                        cornerRadius={1}
                        isAnimationActive={false}
                      >
                        {severityBreakdown.outerRing.map((entry) => (
                          <Cell key={entry.id} fill={entry.color} stroke="hsl(220, 25%, 7%)" strokeWidth={1} fillOpacity={0.55} />
                        ))}
                      </Pie>
                      <Pie
                        data={severityBreakdown.innerRing}
                        dataKey="value"
                        nameKey="name"
                        cx="50%"
                        cy="50%"
                        innerRadius={SEVERITY_INNER_RING_INNER_RADIUS}
                        outerRadius={SEVERITY_INNER_RING_OUTER_RADIUS}
                        paddingAngle={2}
                        cornerRadius={2}
                        isAnimationActive={false}
                      >
                        {severityBreakdown.innerRing.map((entry) => (
                          <Cell key={entry.id} fill={entry.color} stroke="hsl(220, 25%, 7%)" strokeWidth={2} />
                        ))}
                      </Pie>
                      <Tooltip
                        content={({ active, payload }) => {
                          if (!active || !payload?.length) return null;
                          const d = payload[0]?.payload as SeverityRingDatum | undefined;
                          if (!d) return null;
                          const desc = d.fullId ? getRuleDescription(d.fullId) : null;
                          return (
                            <div className="bg-card border border-border rounded px-3 py-2 text-xs font-mono shadow-lg">
                              <div className="font-semibold">{d.fullId || d.name}</div>
                              {desc && <div className="text-muted-foreground font-sans mt-0.5">{desc}</div>}
                              <div className="text-muted-foreground mt-1">Count: {d.value.toLocaleString()}</div>
                            </div>
                          );
                        }}
                      />
                      <Legend
                        payload={severityBreakdown.innerRing.map((d) => ({
                          value: d.name,
                          color: d.color,
                        }))}
                        wrapperStyle={LEGEND_WRAPPER}
                        iconType="circle"
                        iconSize={6}
                      />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                <div className="min-w-0 border-l border-border/70 pl-3 py-2">
                  <div className="text-[9px] text-muted-foreground uppercase tracking-wider mb-2">Outer ring</div>
                  <div className="space-y-1.5">
                    {severityBreakdown.outerRing.map((d) => (
                      <div
                        key={d.id}
                        className="grid grid-cols-[7px_minmax(0,1fr)_auto] items-start gap-1.5 text-[9px] leading-tight"
                        title={`${d.fullId}: ${getRuleDescription(d.fullId ?? d.name) ?? d.name}`}
                      >
                        <span className="mt-1 h-1.5 w-1.5 rounded-full" style={{ backgroundColor: d.color }} />
                        <span className="truncate text-muted-foreground">{d.description}</span>
                        <span className="font-mono text-foreground/70">{d.value.toLocaleString()}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <div className="flex h-[calc(100%-1rem)] min-h-[292px] items-center justify-center text-muted-foreground text-xs">
                No severity data
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Duplication lens — hidden when all zeros */}
      {duplicationByRule.some((d) => d.count > 0) && (
        <div className="border border-border rounded-md bg-card/30 p-3">
          <h4 className="text-[10px] text-muted-foreground uppercase tracking-wider mb-2">Duplication Family</h4>
          <div className="flex flex-wrap gap-3">
            {duplicationByRule.map((d) => (
              <div key={d.rule_id} className="flex items-center gap-2 px-3 py-2 rounded-sm bg-muted/30 border border-border">
                <span className="text-xs whitespace-nowrap">{d.rule_id}</span>
                <span
                  className={cn(
                    "text-sm font-semibold ml-2",
                    d.count > 20 ? "text-signal-ask" : d.count > 5 ? "text-foreground" : "text-muted-foreground",
                  )}
                >
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
