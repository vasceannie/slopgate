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
  eventualRecoveryRate: null,
  recoveryChains: 0,
  recoveredChains: 0,
  abandonedChains: 0,
  openChains: 0,
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
});
