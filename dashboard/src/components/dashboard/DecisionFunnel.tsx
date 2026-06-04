import { ResponsiveLine } from "@nivo/line";
import { ResponsiveBar } from "@nivo/bar";
import type { EventName, Decision } from "@/types/slopgate";
import { DECISION_COLORS, NIVO_DARK_THEME } from "@/lib/chartTheme";

interface Props {
  timeSeries: Array<{ time: string } & Record<Decision, number>>;
  eventsByType: Record<string, number>;
}

const DECISIONS: Decision[] = ["allow", "deny", "block", "ask", "warn", "context"];

export function DecisionFunnel({ timeSeries, eventsByType }: Props) {
  const lineData = DECISIONS.map(d => ({
    id: d,
    color: DECISION_COLORS[d],
    data: timeSeries.map(t => ({
      x: new Date(t.time).toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "numeric" }),
      y: t[d] || 0,
    })),
  }));

  const funnelStages: EventName[] = ["SessionStart", "PreToolUse", "PermissionRequest", "PostToolUse", "Stop"];
  const funnelData = funnelStages.map((stage) => ({
    id: stage,
    value: eventsByType[stage] || 0,
    label: stage.replace(/([A-Z])/g, " $1").trim(),
  }));

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-xs text-muted-foreground uppercase tracking-wider mb-2 px-1">Decision Volume Over Time</h3>
        <div className="h-[200px] border border-border rounded-md bg-card/30 p-2">
          {timeSeries.length > 0 ? (
            <ResponsiveLine
              data={lineData}
              margin={{ top: 10, right: 80, bottom: 30, left: 40 }}
              xScale={{ type: "point" }}
              yScale={{ type: "linear", stacked: true }}
              curve="monotoneX"
              enableArea={true}
              areaOpacity={0.3}
              colors={DECISIONS.map(d => DECISION_COLORS[d])}
              enablePoints={false}
              enableGridX={false}
              gridYValues={4}
              axisBottom={{ tickRotation: -45, tickSize: 0, tickPadding: 8 }}
              axisLeft={{ tickSize: 0, tickPadding: 8, tickValues: 4 }}
              theme={NIVO_DARK_THEME}
              legends={[{
                anchor: "bottom-right", direction: "column", translateX: 80,
                itemWidth: 70, itemHeight: 16, itemTextColor: "hsl(215, 12%, 50%)",
                symbolSize: 8, symbolShape: "circle",
              }]}
            />
          ) : (
            <div className="flex items-center justify-center h-full text-muted-foreground text-xs">No data in window</div>
          )}
        </div>
      </div>

      <div>
        <h3 className="text-xs text-muted-foreground uppercase tracking-wider mb-2 px-1">Event Pipeline</h3>
        <div className="h-[180px] border border-border rounded-md bg-card/30 p-2">
          {funnelData.some(d => d.value > 0) ? (
            <ResponsiveBar
              data={funnelData}
              keys={["value"]}
              indexBy="label"
              layout="vertical"
              margin={{ top: 10, right: 10, bottom: 40, left: 50 }}
              padding={0.35}
              colors={["hsl(142, 50%, 45%)", "hsl(217, 91%, 60%)", "hsl(38, 92%, 50%)", "hsl(300, 70%, 55%)", "hsl(215, 12%, 50%)"]}
              colorBy="indexValue"
              borderWidth={1}
              borderColor="hsl(220, 15%, 15%)"
              enableLabel={true}
              labelTextColor="hsl(210, 20%, 95%)"
              enableGridX={false}
              gridYValues={4}
              axisBottom={{ tickRotation: -25, tickSize: 0, tickPadding: 8 }}
              axisLeft={{ tickSize: 0, tickPadding: 8, tickValues: 4 }}
              theme={NIVO_DARK_THEME}
            />
          ) : (
            <div className="flex items-center justify-center h-full text-muted-foreground text-xs">No data in window</div>
          )}
        </div>
      </div>
    </div>
  );
}