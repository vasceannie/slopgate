import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import Dashboard from "./Dashboard";

type MockTabsState = {
  value: string;
  setValue: (value: string) => void;
};

type MockTabsProps = {
  children?: ReactNode;
  className?: string;
  defaultValue?: string;
};

type MockTabsValueProps = {
  children?: ReactNode;
  className?: string;
  value: string;
};

vi.mock("@/components/ui/tabs", async () => {
  const React = await import("react");
  const TabsContext = React.createContext<MockTabsState | null>(null);

  function useTabsState() {
    const state = React.useContext(TabsContext);
    if (state === null) {
      throw new Error("Tabs components must be rendered inside Tabs");
    }
    return state;
  }

  function Tabs({ children, className, defaultValue = "" }: MockTabsProps) {
    const [value, setValue] = React.useState(defaultValue);
    return (
      <TabsContext.Provider value={{ value, setValue }}>
        <div className={className}>{children}</div>
      </TabsContext.Provider>
    );
  }

  function TabsList({ children, className }: MockTabsProps) {
    return (
      <div className={className} role="tablist">
        {children}
      </div>
    );
  }

  function TabsTrigger({ children, className, value }: MockTabsValueProps) {
    const state = useTabsState();
    return (
      <button aria-selected={state.value === value} className={className} onClick={() => state.setValue(value)} role="tab" type="button">
        {children}
      </button>
    );
  }

  function TabsContent({ children, className, value }: MockTabsValueProps) {
    return useTabsState().value === value ? (
      <div className={className} role="tabpanel">
        {children}
      </div>
    ) : null;
  }

  return { Tabs, TabsContent, TabsList, TabsTrigger };
});

vi.mock("@/components/dashboard/AsyncJobs", () => ({
  AsyncJobs: () => <section>Async quality checks</section>,
}));

vi.mock("@/components/dashboard/DecisionFunnel", () => ({
  DecisionFunnel: () => <section>Decision funnel</section>,
}));

vi.mock("@/components/dashboard/DriftTuning", () => ({
  DriftTuning: () => <section>Drift tuning panel</section>,
}));

vi.mock("@/components/dashboard/FileDropZone", () => ({
  FileDropZone: () => <div>File drop zone</div>,
}));

vi.mock("@/components/dashboard/FalsePositiveAnalysis", () => ({
  FalsePositiveAnalysis: () => <section>False positive analysis</section>,
}));

vi.mock("@/components/dashboard/OpsPostureStrip", () => ({
  OpsPostureStrip: () => <section>Ops posture strip</section>,
}));

vi.mock("@/components/dashboard/PathExplorer", () => ({
  PathExplorer: () => <section>Path explorer</section>,
}));

vi.mock("@/components/dashboard/PostureStrip", () => ({
  PostureStrip: () => <section>Posture strip</section>,
}));

vi.mock("@/components/dashboard/RuleManager", () => ({
  RuleManager: () => <section>Rule manager</section>,
}));

vi.mock("@/components/dashboard/SessionExplorer", () => ({
  SessionExplorer: () => <section>Session explorer</section>,
}));

vi.mock("@/components/dashboard/TimeWindowSelector", () => ({
  TimeWindowSelector: () => <div>Time window selector</div>,
}));

vi.mock("@/components/dashboard/TopRules", () => ({
  TopRules: () => <section>Top rules</section>,
}));

vi.mock("@/hooks/useHarnessStatus", () => ({
  useHarnessStatus: () => ({ status: { ok: true, platforms: [] }, loading: false, error: null }),
}));

vi.mock("@/hooks/useTraceData", () => ({
  useTraceData: () => ({
    async: { passCount: 0, failCount: 0, byCommand: [] },
    drift: {
      config: {},
      hottestRepos: [],
      operationalContext: {
        platformCapabilities: [],
        enforcementModes: [],
        degradedReasons: [],
        repoRoots: [],
        pathlessResults: 0,
        repeatedDenials: [],
        eventualRecoveryRate: null,
        recoveryChains: 0,
        recoveredChains: 0,
        abandonedChains: 0,
        openChains: 0,
      },
    },
    duplicationByRule: [],
    eventsByType: {},
    eventsByTypeAndPlatform: {},
    fireCounts: new Map<string, number>(),
    posture: {},
    results: [],
    rules: [],
    sessions: [],
    sourceStatus: { isSnapshotLoading: false, meta: { totalRecords: 1 } },
    timeSeries: [],
    topRules: [],
    unfilteredEvents: [],
    unfilteredRules: [],
  }),
}));

describe("Dashboard ops tab", () => {
  it("omits the async jobs panel when no async jobs ran", async () => {
    render(<Dashboard />);

    fireEvent.click(screen.getByRole("tab", { name: "Async & Drift" }));

    expect(await screen.findByText("Drift tuning panel")).toBeInTheDocument();
    expect(screen.queryByText("Async quality checks")).not.toBeInTheDocument();
  });
});
