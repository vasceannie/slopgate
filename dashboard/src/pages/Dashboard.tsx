import { useState, useCallback, memo } from "react";
import type { FilterState } from "@/types/slopgate";
import { useTraceData } from "@/hooks/useTraceData";
import { TimeWindowSelector } from "@/components/dashboard/TimeWindowSelector";
import { PostureStrip } from "@/components/dashboard/PostureStrip";
import { DecisionFunnel } from "@/components/dashboard/DecisionFunnel";
import { TopRules } from "@/components/dashboard/TopRules";
import { SessionExplorer } from "@/components/dashboard/SessionExplorer";
import { AsyncJobs } from "@/components/dashboard/AsyncJobs";
import { DriftTuning } from "@/components/dashboard/DriftTuning";
import { FalsePositiveAnalysis } from "@/components/dashboard/FalsePositiveAnalysis";
import { FileDropZone } from "@/components/dashboard/FileDropZone";
import { PathExplorer } from "@/components/dashboard/PathExplorer";
import { RuleManager } from "@/components/dashboard/RuleManager";
import { Terminal, Filter, X, Settings2 } from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";

// Memo wrappers — only for components that aren't already memo'd internally
const MemoPostureStrip = memo(PostureStrip);
const MemoDecisionFunnel = memo(DecisionFunnel);
const MemoTopRules = TopRules;
const MemoAsyncJobs = memo(AsyncJobs);
const MemoDriftTuning = memo(DriftTuning);
// SessionExplorer, FalsePositiveAnalysis, PathExplorer already use memo internally — no double wrapping

export default function Dashboard() {
  const [filters, setFilters] = useState<FilterState>({
    timeWindow: "7d",
    platforms: [],
    pathFilter: null,
  });

  const data = useTraceData(filters);

  const handlePathFilter = useCallback((path: string | null) => {
    setFilters(prev => ({ ...prev, pathFilter: path }));
  }, []);

  return (
    <div className="min-h-screen bg-background">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-3 border-b border-border">
        <div className="flex items-center gap-3">
          <Terminal className="w-5 h-5 text-primary" />
          <h1 className="text-sm font-semibold tracking-wide">
            <span className="text-primary">slopgate</span>
            <span className="text-muted-foreground ml-1.5">flight recorder</span>
          </h1>
        </div>
        {filters.pathFilter && (
          <button
            onClick={() => handlePathFilter(null)}
            className="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-md bg-primary/10 text-primary border border-primary/20 hover:bg-primary/20 transition-colors"
          >
            <Filter className="w-3 h-3" />
            Filtered: <span className="font-mono">{filters.pathFilter}</span>
            <X className="w-3 h-3" />
          </button>
        )}
      </div>

      {/* File upload + Filters */}
      <div className="px-6 pt-4 space-y-3">
        <FileDropZone />
        <TimeWindowSelector filters={filters} onChange={setFilters} />
      </div>

      {/* Posture strip always visible */}
      <div className="px-6 pt-4">
        <MemoPostureStrip data={data.posture} sourceStatus={data.sourceStatus} />
      </div>

      {/* Tabbed content */}
      <div className="px-6 pt-4 pb-6">
        <Tabs defaultValue="overview" className="w-full">
          <TabsList className="bg-secondary border border-border w-full justify-start gap-0 h-9 rounded-lg">
            <TabsTrigger value="overview" className="text-xs data-[state=active]:bg-primary/15 data-[state=active]:text-primary rounded-md">
              Overview
            </TabsTrigger>
            <TabsTrigger value="fp-analysis" className="text-xs data-[state=active]:bg-primary/15 data-[state=active]:text-primary rounded-md">
              FP / FN Analysis
            </TabsTrigger>
            <TabsTrigger value="paths" className="text-xs data-[state=active]:bg-primary/15 data-[state=active]:text-primary rounded-md">
              Paths & Files
            </TabsTrigger>
            <TabsTrigger value="sessions" className="text-xs data-[state=active]:bg-primary/15 data-[state=active]:text-primary rounded-md">
              Sessions
            </TabsTrigger>
            <TabsTrigger value="ops" className="text-xs data-[state=active]:bg-primary/15 data-[state=active]:text-primary rounded-md">
              Async & Drift
            </TabsTrigger>
            <TabsTrigger value="rules" className="text-xs data-[state=active]:bg-primary/15 data-[state=active]:text-primary rounded-md flex items-center gap-1">
              <Settings2 className="w-3 h-3" />Rules
            </TabsTrigger>
          </TabsList>

          <TabsContent value="overview" className="mt-4 space-y-6">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <MemoDecisionFunnel timeSeries={data.timeSeries} eventsByType={data.eventsByType} />
              <MemoTopRules topRules={data.topRules} duplicationByRule={data.duplicationByRule} />
            </div>
          </TabsContent>

          <TabsContent value="fp-analysis" className="mt-4">
            <FalsePositiveAnalysis rules={data.rules} results={data.results} />
          </TabsContent>

          <TabsContent value="paths" className="mt-4">
            <PathExplorer
              events={data.unfilteredEvents}
              rules={data.unfilteredRules}
              onPathFilter={handlePathFilter}
              activePathFilter={filters.pathFilter}
            />
          </TabsContent>

          <TabsContent value="sessions" className="mt-4">
            <SessionExplorer sessions={data.sessions} />
          </TabsContent>

          <TabsContent value="ops" className="mt-4">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <MemoAsyncJobs {...data.async} />
              <MemoDriftTuning config={data.drift.config} hottestRepos={data.drift.hottestRepos} operationalContext={data.drift.operationalContext} />
            </div>
          </TabsContent>

          <TabsContent value="rules" className="mt-4">
            <RuleManager fireCounts={data.fireCounts} />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}