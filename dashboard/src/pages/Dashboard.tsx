import { Filter, LoaderCircle, Settings2, Terminal, X } from "lucide-react";
import { lazy, memo, Suspense, useCallback, useState } from "react";
import type { ReactNode } from "react";
import { DecisionFunnel } from "@/components/dashboard/DecisionFunnel";
import { FileDropZone } from "@/components/dashboard/FileDropZone";
import { PostureStrip } from "@/components/dashboard/PostureStrip";
import { TimeWindowSelector } from "@/components/dashboard/TimeWindowSelector";
import { TopRules } from "@/components/dashboard/TopRules";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useTraceData } from "@/hooks/useTraceData";
import type { FilterState } from "@/types/slopgate";

// Memo wrappers — only for components that aren't already memo'd internally
const MemoPostureStrip = memo(PostureStrip);
const MemoDecisionFunnel = memo(DecisionFunnel);
const MemoTopRules = TopRules;
// SessionExplorer, FalsePositiveAnalysis, PathExplorer already use memo internally — no double wrapping

const LazyAsyncJobs = lazy(() =>
	import("@/components/dashboard/AsyncJobs").then((module) => ({
		default: module.AsyncJobs,
	})),
);
const LazyDriftTuning = lazy(() =>
	import("@/components/dashboard/DriftTuning").then((module) => ({
		default: module.DriftTuning,
	})),
);
const LazyFalsePositiveAnalysis = lazy(() =>
	import("@/components/dashboard/FalsePositiveAnalysis").then((module) => ({
		default: module.FalsePositiveAnalysis,
	})),
);
const LazyPathExplorer = lazy(() =>
	import("@/components/dashboard/PathExplorer").then((module) => ({
		default: module.PathExplorer,
	})),
);
const LazyRuleManager = lazy(() =>
	import("@/components/dashboard/RuleManager").then((module) => ({
		default: module.RuleManager,
	})),
);
const LazySessionExplorer = lazy(() =>
	import("@/components/dashboard/SessionExplorer").then((module) => ({
		default: module.SessionExplorer,
	})),
);

function DashboardTabLoadingPlaceholder() {
	return (
		<div className="flex min-h-[320px] items-center justify-center rounded-md border border-border bg-card/30 p-3 text-xs text-muted-foreground">
			<LoaderCircle className="mr-2 h-4 w-4 animate-spin text-primary" />
			Loading panel…
		</div>
	);
}

function LazyTab({ children }: { children: ReactNode }) {
	return (
		<Suspense fallback={<DashboardTabLoadingPlaceholder />}>{children}</Suspense>
	);
}

function OverviewLoadingPlaceholder() {
	return (
		<div className="grid grid-cols-1 items-stretch gap-6 lg:grid-cols-2">
			<div className="grid min-h-[590px] gap-4 lg:h-[650px] lg:grid-rows-[minmax(260px,1.12fr)_minmax(220px,0.88fr)]">
				{["Decision Volume Over Time", "Event Pipeline"].map((label) => (
					<div key={label}>
						<h3 className="text-xs text-muted-foreground uppercase tracking-wider mb-2 px-1">
							{label}
						</h3>
						<div className="flex h-[calc(100%-1.25rem)] min-h-[220px] items-center justify-center rounded-md border border-border bg-card/30 p-3 text-xs text-muted-foreground">
							<LoaderCircle className="mr-2 h-4 w-4 animate-spin text-primary" />
							Loading live trace snapshot…
						</div>
					</div>
				))}
			</div>
			<div className="space-y-3">
				<div className="flex min-h-[590px] flex-col gap-3 lg:h-[650px]">
					<div className="flex items-center justify-between">
						<h3 className="text-xs text-muted-foreground uppercase tracking-wider px-1">
							Top Pressure Rules
						</h3>
					</div>
					<div className="grid min-h-0 flex-1 grid-rows-[minmax(245px,0.43fr)_minmax(320px,0.57fr)] gap-4">
						{["Top Pressure Rules", "Severity Mix"].map((label) => (
							<div
								key={label}
								className="flex min-h-0 items-center justify-center rounded-md border border-border bg-card/30 p-3 text-xs text-muted-foreground"
							>
								<LoaderCircle className="mr-2 h-4 w-4 animate-spin text-primary" />
								Loading {label.toLowerCase()}…
							</div>
						))}
					</div>
				</div>
			</div>
		</div>
	);
}

export default function Dashboard() {
	const [filters, setFilters] = useState<FilterState>({
		timeWindow: "7d",
		platforms: [],
		pathFilter: null,
	});

	const data = useTraceData(filters);
	const isInitialSnapshotLoading =
		data.sourceStatus.isSnapshotLoading &&
		data.sourceStatus.meta.totalRecords === 0;

	const handlePathFilter = useCallback((path: string | null) => {
		setFilters((prev) => ({ ...prev, pathFilter: path }));
	}, []);

	return (
		<div className="min-h-screen bg-background">
			{/* Header */}
			<div className="flex items-center justify-between px-6 py-3 border-b border-border">
				<div className="flex items-center gap-3">
					<Terminal className="w-5 h-5 text-primary" />
					<h1 className="text-sm font-semibold tracking-wide">
						<span className="text-primary">slopgate</span>
						<span className="text-muted-foreground ml-1.5">
							flight recorder
						</span>
					</h1>
				</div>
				{filters.pathFilter && (
					<button
						type="button"
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
				<MemoPostureStrip
					data={data.posture}
					sourceStatus={data.sourceStatus}
				/>
			</div>

			{/* Tabbed content */}
			<div className="px-6 pt-4 pb-6">
				<Tabs defaultValue="overview" className="w-full">
					<TabsList className="bg-secondary border border-border w-full justify-start gap-0 h-9 rounded-lg">
						<TabsTrigger
							value="overview"
							className="text-xs data-[state=active]:bg-primary/15 data-[state=active]:text-primary rounded-md"
						>
							Overview
						</TabsTrigger>
						<TabsTrigger
							value="fp-analysis"
							className="text-xs data-[state=active]:bg-primary/15 data-[state=active]:text-primary rounded-md"
						>
							FP / FN Analysis
						</TabsTrigger>
						<TabsTrigger
							value="paths"
							className="text-xs data-[state=active]:bg-primary/15 data-[state=active]:text-primary rounded-md"
						>
							Paths & Files
						</TabsTrigger>
						<TabsTrigger
							value="sessions"
							className="text-xs data-[state=active]:bg-primary/15 data-[state=active]:text-primary rounded-md"
						>
							Sessions
						</TabsTrigger>
						<TabsTrigger
							value="ops"
							className="text-xs data-[state=active]:bg-primary/15 data-[state=active]:text-primary rounded-md"
						>
							Async & Drift
						</TabsTrigger>
						<TabsTrigger
							value="rules"
							className="text-xs data-[state=active]:bg-primary/15 data-[state=active]:text-primary rounded-md flex items-center gap-1"
						>
							<Settings2 className="w-3 h-3" />
							Rules
						</TabsTrigger>
					</TabsList>

					<TabsContent value="overview" className="mt-4 space-y-6">
						{isInitialSnapshotLoading ? (
							<OverviewLoadingPlaceholder />
						) : (
							<div className="grid grid-cols-1 items-stretch gap-6 lg:grid-cols-2">
								<MemoDecisionFunnel
									timeSeries={data.timeSeries}
									eventsByType={data.eventsByType}
									eventsByTypeAndPlatform={data.eventsByTypeAndPlatform}
									timeWindow={filters.timeWindow}
								/>
								<MemoTopRules
									topRules={data.topRules}
									duplicationByRule={data.duplicationByRule}
								/>
							</div>
						)}
					</TabsContent>

					<TabsContent value="fp-analysis" className="mt-4">
						<LazyTab>
							<LazyFalsePositiveAnalysis
								rules={data.rules}
								results={data.results}
							/>
						</LazyTab>
					</TabsContent>

					<TabsContent value="paths" className="mt-4">
						<LazyTab>
							<LazyPathExplorer
								events={data.unfilteredEvents}
								rules={data.unfilteredRules}
								onPathFilter={handlePathFilter}
								activePathFilter={filters.pathFilter}
							/>
						</LazyTab>
					</TabsContent>

					<TabsContent value="sessions" className="mt-4">
						<LazyTab>
							<LazySessionExplorer sessions={data.sessions} />
						</LazyTab>
					</TabsContent>

					<TabsContent value="ops" className="mt-4">
						<LazyTab>
							<div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
								<LazyAsyncJobs {...data.async} />
								<LazyDriftTuning
									config={data.drift.config}
									hottestRepos={data.drift.hottestRepos}
									operationalContext={data.drift.operationalContext}
								/>
							</div>
						</LazyTab>
					</TabsContent>

					<TabsContent value="rules" className="mt-4">
						<LazyTab>
							<LazyRuleManager fireCounts={data.fireCounts} />
						</LazyTab>
					</TabsContent>
				</Tabs>
			</div>
		</div>
	);
}
