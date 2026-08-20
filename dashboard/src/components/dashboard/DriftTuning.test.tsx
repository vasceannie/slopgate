import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { HarnessStatusState } from "@/hooks/useHarnessStatus";
import type { OperationalContext, RuntimeConfig } from "@/types/slopgate";
import { DriftTuning } from "./DriftTuning";

const CONFIG: RuntimeConfig = {
  disabled_rules: [],
  severity_overrides: [],
  skip_paths: [],
  skip_repos: [],
};

const HARNESS_STATUS: HarnessStatusState = {
  status: { ok: true, platforms: [] },
  loading: false,
  error: null,
};

const OPERATIONAL_CONTEXT: OperationalContext = {
  platformCapabilities: [],
  enforcementModes: [],
  degradedReasons: [],
  repoRoots: [],
  pathlessResults: 0,
  repeatedDenials: [],
  resolutionRate: null,
  blockedSessions: 0,
  resolvedBlockedSessions: 0,
  censoredRepairEpisodes: 0,
  scopeConfidence: [],
  authoritativeResults: 0,
  legacyResults: 0,
};

describe("DriftTuning", () => {
  it("scales highest hook volume against the largest displayed repo", () => {
    render(
      <DriftTuning
        config={CONFIG}
        harnessStatus={HARNESS_STATUS}
        hottestRepos={[
          { repo: "smaller", count: 5 },
          { repo: "larger", count: 10 },
        ]}
        operationalContext={OPERATIONAL_CONTEXT}
      />,
    );

    expect(screen.getByText("50% (5)")).toBeInTheDocument();
    expect(screen.getByText("100% (10)")).toBeInTheDocument();
    expect(screen.queryByText("200% (10)")).not.toBeInTheDocument();
  });

  it("labels repair outcomes and provenance confidence explicitly", () => {
    render(
      <DriftTuning
        config={CONFIG}
        harnessStatus={HARNESS_STATUS}
        hottestRepos={[]}
        operationalContext={{
          ...OPERATIONAL_CONTEXT,
          resolutionRate: 50,
          blockedSessions: 2,
          resolvedBlockedSessions: 1,
          censoredRepairEpisodes: 2,
          scopeConfidence: [
            { label: "high", count: 1 },
            { label: "medium", count: 1 },
          ],
          authoritativeResults: 3,
          legacyResults: 1,
        }}
      />,
    );

    expect(screen.getByText("Observed Repair Success")).toBeInTheDocument();
    expect(screen.getByText("1/2 comparable rule-local repair episodes resolved.")).toBeInTheDocument();
    expect(screen.getByText("2 censored episodes excluded.")).toBeInTheDocument();
    expect(screen.getByText("3 authoritative · 1 legacy/unknown-policy")).toBeInTheDocument();
  });
});
