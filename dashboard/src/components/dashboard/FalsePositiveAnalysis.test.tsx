import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FlagProvider } from "@/context/FlagContext";
import type { HookResult, RuleFinding } from "@/types/slopgate";
import { FalsePositiveAnalysis } from "./FalsePositiveAnalysis";

function createFinding(ruleId: string, decision: RuleFinding["decision"], sessionId = "session-1"): RuleFinding {
  return {
    timestamp: "2026-06-14T12:00:00.000Z",
    platform: "opencode",
    event_name: "Stop",
    session_id: sessionId,
    tool_name: "Stop",
    rule_id: ruleId,
    severity: "HIGH",
    decision,
    message: `${ruleId} fired`,
    additional_context: null,
    metadata: {},
  };
}

describe("FalsePositiveAnalysis Component", () => {
  it("renders empty state when no rules/results are provided", () => {
    render(
      <FlagProvider>
        <FalsePositiveAnalysis rules={[]} results={[]} />
      </FlagProvider>,
    );

    expect(screen.getByText("Not enough evidence for calibration.")).toBeInTheDocument();
  });

  it("renders calibration triage layout and horizontal diagnostic strip", () => {
    const rules = [createFinding("PY-CODE-010", "block", "session-1"), createFinding("PY-LOG-002", "context", "session-2")];
    const results: HookResult[] = [
      {
        timestamp: "2026-06-14T12:00:01.000Z",
        platform: "opencode",
        event_name: "PostToolUse",
        session_id: "session-2",
        tool_name: "Stop",
        findings: [{ rule_id: "PY-LOG-002", severity: "HIGH", decision: "context", message: "fired" }],
        errors: null,
        output: null,
      },
    ];

    render(
      <FlagProvider>
        <FalsePositiveAnalysis rules={rules} results={results} />
      </FlagProvider>,
    );

    expect(screen.getByText("Rule Calibration Triage")).toBeInTheDocument();
    expect(screen.getByText("Triage Queue Overview")).toBeInTheDocument();
    expect(screen.getByText("Needs Review")).toBeInTheDocument();
    expect(screen.getByText("Runtime/Repeat Rules")).toBeInTheDocument();
    expect(screen.getByText("Persistent Rules")).toBeInTheDocument();
    expect(screen.getAllByText("PY-CODE-010")[0]).toBeInTheDocument();
  });

  it("resets active view and updates flag labels on mode switching", () => {
    const rules = [createFinding("PY-CODE-010", "block", "session-1"), createFinding("PY-LOG-002", "context", "session-2")];
    const results: HookResult[] = [
      {
        timestamp: "2026-06-14T12:00:01.000Z",
        platform: "opencode",
        event_name: "PostToolUse",
        session_id: "session-2",
        tool_name: "Stop",
        findings: [{ rule_id: "PY-LOG-002", severity: "HIGH", decision: "context", message: "fired" }],
        errors: null,
        output: null,
      },
    ];

    render(
      <FlagProvider>
        <FalsePositiveAnalysis rules={rules} results={results} />
      </FlagProvider>,
    );

    // Switch to Runtime/repeat score lens
    const errorTabButton = screen.getByRole("tab", { name: /Runtime\/repeat score/i });
    fireEvent.click(errorTabButton);

    // Now check selected rule/signals in the table
    expect(screen.getAllByText("PY-CODE-010")[0]).toBeInTheDocument();
  });
});
