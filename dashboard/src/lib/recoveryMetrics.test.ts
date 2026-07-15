import { describe, expect, it } from "vitest";
import type { HookResult } from "@/types/slopgate";
import { computeRecoveryMetrics } from "./recoveryMetrics";

const DENIAL: HookResult = {
  timestamp: "2026-07-14T12:00:00.000Z",
  platform: "opencode",
  event_name: "PreToolUse",
  session_id: "session-1",
  tool_name: "Edit",
  findings: [{ rule_id: "RULE-001", severity: "HIGH", decision: "deny", message: "blocked" }],
  errors: null,
  output: null,
  trace_schema_version: 2,
  evaluation_id: "deny-1",
  correlation_confidence: "inferred",
  candidate_paths: ["src/app.py"],
  attempt_fingerprint: "a",
  event_outcome: "blocked_pre_tool",
  tool_outcome: "unknown",
  resolved_repo_root: "/repo",
  enforcement_mode: "repo_strict",
};

const SUCCESS: HookResult = {
  ...DENIAL,
  timestamp: "2026-07-14T12:01:00.000Z",
  event_name: "PostToolUse",
  evaluation_id: "success-1",
  findings: [],
  event_outcome: "passed_clean",
  tool_outcome: "success",
};

describe("computeRecoveryMetrics", () => {
  it("recovers only after successful same-target completion", () => {
    expect(computeRecoveryMetrics([DENIAL, SUCCESS])).toEqual({
      chains: 1,
      recovered: 1,
      abandoned: 0,
      open: 0,
      eventualRecoveryRate: 100,
    });
  });

  it("keeps later advisory-only activity open", () => {
    const advisory: HookResult = {
      ...SUCCESS,
      event_name: "PreToolUse",
      tool_outcome: "unknown",
      findings: [{ rule_id: "GUIDANCE", severity: "LOW", decision: "context", message: "hint" }],
    };

    expect(computeRecoveryMetrics([DENIAL, advisory])).toEqual({
      chains: 1,
      recovered: 0,
      abandoned: 0,
      open: 1,
      eventualRecoveryRate: null,
    });
  });

  it("marks explicit terminal closure as abandonment", () => {
    const terminal: HookResult = {
      ...SUCCESS,
      event_name: "Stop",
      tool_outcome: "unknown",
      candidate_paths: [],
    };

    expect(computeRecoveryMetrics([DENIAL, terminal])).toEqual({
      chains: 1,
      recovered: 0,
      abandoned: 1,
      open: 0,
      eventualRecoveryRate: 0,
    });
  });

  it("does not correlate successful completion on another target", () => {
    const otherTarget: HookResult = { ...SUCCESS, candidate_paths: ["src/other.py"] };

    expect(computeRecoveryMetrics([DENIAL, otherTarget])).toEqual({
      chains: 1,
      recovered: 0,
      abandoned: 0,
      open: 1,
      eventualRecoveryRate: null,
    });
  });

  it("keeps a successful post-tool event with another blocking finding open", () => {
    const blockedPostTool: HookResult = {
      ...SUCCESS,
      event_outcome: "blocked_post_tool",
      findings: [{ rule_id: "RULE-002", severity: "HIGH", decision: "deny", message: "still blocked" }],
    };

    expect(computeRecoveryMetrics([DENIAL, blockedPostTool])).toEqual({
      chains: 2,
      recovered: 0,
      abandoned: 0,
      open: 2,
      eventualRecoveryRate: null,
    });
  });

  it("starts a chain only for the finding-specific path", () => {
    const multiTargetDenial: HookResult = {
      ...DENIAL,
      candidate_paths: ["src/app.py", "src/other.py"],
      findings: [
        {
          rule_id: "RULE-001",
          severity: "HIGH",
          decision: "deny",
          message: "blocked",
          metadata: { path: "src/app.py" },
        },
      ],
    };

    expect(computeRecoveryMetrics([multiTargetDenial])).toEqual({
      chains: 1,
      recovered: 0,
      abandoned: 0,
      open: 1,
      eventualRecoveryRate: null,
    });
  });

  it("keeps quality lint collector variants as separate chains", () => {
    const qualityDenial: HookResult = {
      ...DENIAL,
      findings: [
        {
          rule_id: "QUALITY-LINT-001",
          severity: "HIGH",
          decision: "deny",
          message: "quality failed",
          metadata: { failing_collectors: ["long-method", "duplicate-code"] },
        },
      ],
    };

    expect(computeRecoveryMetrics([qualityDenial])).toEqual({
      chains: 2,
      recovered: 0,
      abandoned: 0,
      open: 2,
      eventualRecoveryRate: null,
    });
  });

  it("uses the first quality metadata hit when path is a sentinel", () => {
    const denialWithHit: HookResult = {
      ...DENIAL,
      candidate_paths: ["src/unrelated.py"],
      findings: [
        {
          rule_id: "RULE-001",
          severity: "HIGH",
          decision: "deny",
          message: "blocked",
          metadata: { path: "patch.diff", hits: ["content", "src/app.py"] },
        },
      ],
    };

    expect(computeRecoveryMetrics([denialWithHit, SUCCESS])).toEqual({
      chains: 1,
      recovered: 1,
      abandoned: 0,
      open: 0,
      eventualRecoveryRate: 100,
    });
  });

  it("caps oversized trace records at 256 recovery chains", () => {
    const oversizedDenial: HookResult = {
      ...DENIAL,
      candidate_paths: Array.from({ length: 33 }, (_unused, index) => `src/path-${index}.py`),
      findings: Array.from({ length: 65 }, (_unused, findingIndex) => ({
        rule_id: "QUALITY-LINT-001",
        severity: "HIGH" as const,
        decision: "deny" as const,
        message: `blocked-${findingIndex}`,
        metadata: {
          failing_collectors: Array.from({ length: 17 }, (_item, index) => `collector-${index}`),
        },
      })),
    };

    expect(computeRecoveryMetrics([oversizedDenial])).toMatchObject({
      chains: 256,
      recovered: 0,
      abandoned: 0,
      open: 256,
    });
  });

  it("applies the finding cap before selecting blocking findings", () => {
    const advisoryFindings = Array.from({ length: 64 }, (_unused, index) => ({
      rule_id: `GUIDANCE-${index}`,
      severity: "LOW" as const,
      decision: "context" as const,
      message: "hint",
    }));
    const denialAfterLimit: HookResult = {
      ...DENIAL,
      findings: [...advisoryFindings, DENIAL.findings[0]],
    };

    expect(computeRecoveryMetrics([denialAfterLimit])).toMatchObject({
      chains: 0,
      open: 0,
    });
  });

  it("deduplicates paths and collectors before applying their limits", () => {
    const duplicatedInputs: HookResult = {
      ...DENIAL,
      candidate_paths: [...Array.from({ length: 32 }, () => "src/a.py"), "src/b.py"],
      findings: [
        {
          rule_id: "QUALITY-LINT-001",
          severity: "HIGH",
          decision: "deny",
          message: "quality failed",
          metadata: {
            failing_collectors: [...Array.from({ length: 16 }, () => "long-method"), "duplicate-code"],
          },
        },
      ],
    };

    expect(computeRecoveryMetrics([duplicatedInputs])).toMatchObject({
      chains: 4,
      open: 4,
    });
  });
});
