import { renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { TraceDataContextValue } from "@/context/traceDataContext";
import { useTraceDataSource } from "@/context/useTraceDataSource";
import type { FilterState, HookEvent, HookResult, Platform, RuleFinding, SubprocessRun } from "@/types/slopgate";
import { buildTraceSessionIndexes, streamSchemaValidationWarning, summarizeTopRules, useTraceData } from "./useTraceData";

vi.mock("@/context/useTraceDataSource", () => ({
  useTraceDataSource: vi.fn(),
}));

const mockedUseTraceDataSource = vi.mocked(useTraceDataSource);

const DEFAULT_FILTERS: FilterState = {
  timeWindow: "30d",
  platforms: [],
  pathFilter: null,
};

function sourceContext(data: TraceDataContextValue["data"]): TraceDataContextValue {
  return {
    data,
    sourceMode: "uploaded",
    streamState: "idle",
    sourceMeta: {
      initialDataLatestAt: null,
      latestDataAt: null,
      snapshotLoadedAt: null,
      snapshotLookbackHours: null,
      snapshotError: null,
      snapshotTruncated: {},
      snapshotSummary: null,
      isSnapshotLoading: false,
      streamConnectedAt: null,
      lastAcceptedStreamRecordAt: null,
      acceptedStreamRecords: 0,
      rejectedStreamRecords: 0,
      totalRecords: data.events.length + data.rules.length + data.results.length + data.subprocesses.length,
    },
    isStreaming: false,
    isLive: false,
    lastStreamEventAt: null,
    ingestFiles: async () => ({ accepted: 0, rejected: [] }),
    refreshSnapshot: async () => {},
    resetToMock: () => {},
  };
}

afterEach(() => {
  vi.useRealTimers();
  mockedUseTraceDataSource.mockReset();
});

function finding(rule_id: string, decision: RuleFinding["decision"]): RuleFinding {
  return {
    timestamp: "2026-05-27T12:00:00.000Z",
    platform: "opencode",
    event_name: "Stop",
    session_id: `session-${rule_id}-${decision ?? "none"}`,
    tool_name: "Stop",
    rule_id,
    severity: "LOW",
    decision,
    message: `${rule_id} ${decision ?? "none"}`,
    additional_context: null,
    metadata: {},
  };
}

function event(session_id: string, platform: Platform = "opencode"): HookEvent {
  return {
    timestamp: "2026-05-27T12:00:00.000Z",
    platform,
    event_name: "PreToolUse",
    session_id,
    tool_name: "Bash",
    candidate_paths: [],
    languages: ["python"],
  };
}

function traceEvent(session_id: string, timestamp: string, platform: Platform, candidate_paths: string[], tool_name = "Read"): HookEvent {
  return {
    timestamp,
    platform,
    event_name: "PreToolUse",
    session_id,
    tool_name,
    candidate_paths,
    languages: ["typescript"],
  };
}

describe("trace top-rule summaries", () => {
  it("prioritizes enforcement deny/block rules ahead of enrichment noise", () => {
    const rules = [
      finding("ENRICHMENT", "context"),
      finding("ENRICHMENT", "context"),
      finding("ENRICHMENT", "context"),
      finding("_ENRICHMENT_METRICS", "info"),
      finding("PY-CODE-018", "block"),
      finding("PY-CODE-013", "deny"),
    ];

    const topRules = summarizeTopRules(rules);

    expect(topRules.map((rule) => rule.rule_id)).toEqual(["PY-CODE-018", "PY-CODE-013", "ENRICHMENT", "_ENRICHMENT_METRICS"]);
    expect(topRules.find((rule) => rule.rule_id === "ENRICHMENT")).toMatchObject({ count: 3, decisions: { context: 3 } });
    expect(topRules.find((rule) => rule.rule_id === "_ENRICHMENT_METRICS")).toMatchObject({ count: 1, decisions: { info: 1 } });
  });

  it("preserves raw advisory telemetry when no enforcement findings exist", () => {
    const rules = [
      finding("ENRICHMENT", "context"),
      finding("PY-CODE-012", "context"),
      finding("PY-CODE-012", "context"),
      finding("_ENRICHMENT_METRICS", "info"),
    ];

    const topRules = summarizeTopRules(rules);

    expect(topRules.map((rule) => rule.rule_id)).toEqual(["PY-CODE-012", "ENRICHMENT", "_ENRICHMENT_METRICS"]);
    expect(topRules).toHaveLength(3);
  });

  it("keeps high-volume advisory rules available after enforcement-heavy sorting", () => {
    const rules = Array.from({ length: 26 }, (_unused, index) => finding(`PY-BLOCK-${index}`, "deny"));
    rules.push(...Array.from({ length: 50 }, () => finding("ADVISORY-HOTSPOT", "context")));

    const topRules = summarizeTopRules(rules);

    expect(topRules.find((rule) => rule.rule_id === "ADVISORY-HOTSPOT")).toMatchObject({
      count: 50,
      decisions: { context: 50 },
    });
  });
});

describe("stream schema validation warning", () => {
  it("does not warn when the live stream is accepting records", () => {
    expect(streamSchemaValidationWarning(8, 254852)).toBeNull();
  });

  it("warns when stream records are rejected before any record is accepted", () => {
    expect(streamSchemaValidationWarning(2, 0)).toBe("2 streamed records failed dashboard schema validation.");
  });
});

describe("useTraceData", () => {
  it("filters self-test records out of dashboard aggregates", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-05-28T12:00:00.000Z"));
    const realEvent = traceEvent("session-real", "2026-05-27T12:00:00.000Z", "opencode", ["/repos/slopgate/src/real.py"], "Bash");
    const selfTestSessionId = "self-test-opencode-GIT-001";
    const selfTestEvent = traceEvent(
      selfTestSessionId,
      "2026-05-27T12:00:01.000Z",
      "opencode",
      ["/repos/slopgate/src/self_test.py"],
      "Bash",
    );
    const selfTestFinding = finding("GIT-001", "deny");
    selfTestFinding.session_id = selfTestSessionId;
    const realResult: HookResult = {
      timestamp: "2026-05-27T12:00:02.000Z",
      platform: "opencode",
      event_name: "PostToolUse",
      session_id: "session-real",
      tool_name: "Bash",
      findings: [],
      errors: null,
      output: null,
    };
    const selfTestResult: HookResult = {
      timestamp: "2026-05-27T12:00:03.000Z",
      platform: "opencode",
      event_name: "PostToolUse",
      session_id: selfTestSessionId,
      tool_name: "Bash",
      findings: [
        {
          rule_id: "GIT-001",
          severity: "HIGH",
          decision: "deny",
          message: "self-test denial",
        },
      ],
      errors: null,
      output: null,
    };
    const selfTestSubprocess: SubprocessRun = {
      timestamp: "2026-05-27T12:00:04.000Z",
      event_name: "PostToolUse",
      session_id: selfTestSessionId,
      command: "slopgate test",
      cwd: "/repos/slopgate",
      returncode: 0,
      stdout: "",
      stderr: "",
      duration_ms: 10,
    };
    mockedUseTraceDataSource.mockReturnValue(
      sourceContext({
        events: [realEvent, selfTestEvent],
        rules: [selfTestFinding],
        results: [realResult, selfTestResult],
        subprocesses: [selfTestSubprocess],
      }),
    );

    const { result } = renderHook(() => useTraceData(DEFAULT_FILTERS));

    expect(result.current.events.map((item) => item.session_id)).toEqual(["session-real"]);
    expect(result.current.rules).toEqual([]);
    expect(result.current.results.map((item) => item.session_id)).toEqual(["session-real"]);
    expect(result.current.subprocesses).toEqual([]);
    expect(result.current.posture.totalInvocations).toBe(1);
    expect(result.current.posture.decisionCounts).toMatchObject({
      allow: 1,
      deny: 0,
    });
    expect(result.current.topRules).toEqual([]);
    expect(result.current.sessions.map((session) => session.id)).toEqual(["session-real"]);
    expect(result.current.async.passCount).toBe(0);
    expect(result.current.fireCounts.has("GIT-001")).toBe(false);
  });
});

describe("trace session indexes", () => {
  it("centralizes session, repo, and decision indexes in one pass", () => {
    const events: HookEvent[] = [
      {
        timestamp: "2026-05-27T12:00:00.000Z",
        platform: "codex",
        event_name: "PreToolUse",
        session_id: "session-a",
        tool_name: "Bash",
        candidate_paths: ["/home/trav/repos/slopgate/src/a.py", "/home/trav/repos/slopgate/src/a.py"],
        languages: ["python"],
      },
    ];
    const rules = [finding("PY-CODE-013", "deny")];
    rules[0].session_id = "session-a";
    const results: HookResult[] = [
      {
        timestamp: "2026-05-27T12:00:01.000Z",
        platform: "codex",
        event_name: "PostToolUse",
        session_id: "session-a",
        tool_name: "Bash",
        findings: [
          {
            rule_id: "PY-CODE-013",
            severity: "MEDIUM",
            decision: "deny",
            message: "blocked",
          },
        ],
        errors: null,
        output: null,
      },
    ];
    const subprocesses: SubprocessRun[] = [
      {
        timestamp: "2026-05-27T12:00:02.000Z",
        event_name: "PostToolUse",
        session_id: "session-a",
        command: "pytest",
        cwd: "/home/trav/repos/slopgate",
        returncode: 0,
        stdout: "",
        stderr: "",
        duration_ms: 25,
      },
    ];

    const indexes = buildTraceSessionIndexes(events, rules, results, subprocesses);

    expect(indexes.sessions).toHaveLength(1);
    expect(indexes.sessions[0]).toMatchObject({
      id: "session-a",
      pathCount: 1,
      finalOutcome: "deny",
      eventCount: 1,
    });
    expect(indexes.sessions[0].subprocesses).toHaveLength(1);
    expect(indexes.sessionPathCounts.get("session-a")).toBe(1);
    expect(indexes.sessionDecisions.get("session-a")).toEqual(["deny"]);
    expect(indexes.hottestRepos).toEqual([{ repo: "slopgate", count: 2 }]);
  });

  it("carries session titles from trace metadata into session rows", () => {
    const titledEvent: HookEvent = {
      ...event("session-with-title", "codex"),
      session_title: "Fix dashboard session labels",
    };

    const indexes = buildTraceSessionIndexes([titledEvent], [], [], []);

    expect(indexes.sessions).toHaveLength(1);
    expect(indexes.sessions[0]).toMatchObject({
      id: "session-with-title",
      title: "Fix dashboard session labels",
    });
  });

  it("carries native and secondary session identities into session rows", () => {
    const identityEvent: HookEvent = {
      ...event("opencode-plugin-synthetic", "opencode"),
      opencode_session_id: "ses_139981ae7ffeOKOMbswUJdo3Oy",
      session_identity_source: "opencode-event",
      secondary_session_ids: ["opencode-plugin-synthetic"],
    };

    const indexes = buildTraceSessionIndexes([identityEvent], [], [], []);

    expect(indexes.sessions).toHaveLength(1);
    expect(indexes.sessions[0]).toMatchObject({
      id: "opencode-plugin-synthetic",
      sessionIdentitySource: "opencode-event",
      secondaryIds: ["opencode-plugin-synthetic"],
      nativeSessionIds: {
        opencode: "ses_139981ae7ffeOKOMbswUJdo3Oy",
      },
    });
  });

  it("groups synthetic OpenCode rows by exact shared native session identity", () => {
    const firstSynthetic: HookEvent = {
      ...event("opencode-plugin-a", "opencode"),
      opencode_session_id: "ses_native_shared",
      session_identity_source: "opencode-event",
    };
    const secondSynthetic: HookEvent = {
      ...event("opencode-plugin-b", "opencode"),
      opencode_session_id: "ses_native_shared",
      session_identity_source: "opencode-event",
    };

    const indexes = buildTraceSessionIndexes([firstSynthetic, secondSynthetic], [], [], []);

    expect(indexes.sessions).toHaveLength(1);
    expect(indexes.sessions[0]).toMatchObject({
      id: "opencode-plugin-a",
      lineageConfidence: "explicit",
      nativeSessionIds: {
        opencode: "ses_native_shared",
      },
    });
    expect(indexes.sessions[0].childSessions).toEqual([]);
    expect(indexes.sessions[0].mirrorSessions).toEqual([]);
    expect([...indexes.sessions[0].rawSessionIds].sort()).toEqual(["opencode-plugin-a", "opencode-plugin-b"]);
    expect(indexes.sessionGroups[0]).toMatchObject({
      id: "opencode-plugin-a",
      lineageConfidence: "explicit",
      rawSessionIds: ["opencode-plugin-a", "opencode-plugin-b"],
    });
  });

  it("groups synthetic Codex rows by exact shared native thread identity", () => {
    const firstSynthetic: HookEvent = {
      ...event("codex-hook-a", "codex"),
      codex_session_id: "thr_native_shared",
      session_identity_source: "codex-thread",
    };
    const secondSynthetic: HookEvent = {
      ...event("codex-hook-b", "codex"),
      codex_session_id: "thr_native_shared",
      session_identity_source: "codex-thread",
    };

    const indexes = buildTraceSessionIndexes([firstSynthetic, secondSynthetic], [], [], []);

    expect(indexes.sessions).toHaveLength(1);
    expect(indexes.sessions[0]).toMatchObject({
      id: "codex-hook-a",
      lineageConfidence: "explicit",
      nativeSessionIds: {
        codex: "thr_native_shared",
      },
    });
    expect([...indexes.sessions[0].rawSessionIds].sort()).toEqual(["codex-hook-a", "codex-hook-b"]);
    expect(indexes.sessionGroups[0]).toMatchObject({
      id: "codex-hook-a",
      lineageConfidence: "explicit",
      rawSessionIds: ["codex-hook-a", "codex-hook-b"],
    });
  });

  it("excludes self-test sessions from dashboard session indexes", () => {
    const realEvent = traceEvent("session-real", "2026-05-27T12:00:00.000Z", "opencode", ["/repos/slopgate/src/real.py"], "Bash");
    const selfTestSessionId = "self-test-opencode-GIT-001";
    const selfTestEvent = traceEvent(
      selfTestSessionId,
      "2026-05-27T12:00:01.000Z",
      "opencode",
      ["/repos/slopgate/src/self_test.py"],
      "Bash",
    );
    const selfTestFinding = finding("GIT-001", "deny");
    selfTestFinding.session_id = selfTestSessionId;
    const selfTestResult: HookResult = {
      timestamp: "2026-05-27T12:00:02.000Z",
      platform: "opencode",
      event_name: "PostToolUse",
      session_id: selfTestSessionId,
      tool_name: "Bash",
      findings: [
        {
          rule_id: "GIT-001",
          severity: "HIGH",
          decision: "deny",
          message: "self-test denial",
        },
      ],
      errors: null,
      output: null,
    };
    const selfTestSubprocess: SubprocessRun = {
      timestamp: "2026-05-27T12:00:03.000Z",
      event_name: "PostToolUse",
      session_id: selfTestSessionId,
      command: "slopgate test",
      cwd: "/repos/slopgate",
      returncode: 0,
      stdout: "",
      stderr: "",
      duration_ms: 10,
    };

    const indexes = buildTraceSessionIndexes([realEvent, selfTestEvent], [selfTestFinding], [selfTestResult], [selfTestSubprocess]);

    expect(indexes.sessions).toHaveLength(1);
    expect(indexes.sessions[0]).toMatchObject({
      id: "session-real",
      eventCount: 1,
      finalOutcome: "allow",
      pathCount: 1,
    });
    expect(indexes.sessionGroups).toHaveLength(1);
    expect(indexes.sessionPathCounts.has(selfTestSessionId)).toBe(false);
    expect(indexes.sessionDecisions.has(selfTestSessionId)).toBe(false);
    expect(indexes.hottestRepos).toEqual([{ repo: "slopgate", count: 1 }]);
  });

  it("handles large sessions without spreading timestamp arrays", () => {
    const start = Date.UTC(2026, 4, 27, 12, 0, 0);
    const events: HookEvent[] = Array.from({ length: 120_000 }, (_unused, index) => ({
      ...event("large-session", "opencode"),
      timestamp: new Date(start + index).toISOString(),
      candidate_paths: ["/home/trav/repos/slopgate/src/large.py"],
    }));

    const indexes = buildTraceSessionIndexes(events, [], [], []);

    expect(indexes.sessions).toHaveLength(1);
    expect(indexes.sessions[0]).toMatchObject({
      id: "large-session",
      eventCount: events.length,
      pathCount: 1,
      duration: events.length - 1,
    });
  });

  it("returns grouped primary rows with child and mirror lineage attached", () => {
    const parent = event("parent-session", "claude");
    const child: HookEvent = {
      ...event("child-session", "opencode"),
      parent_session_id: "parent-session",
      root_session_id: "parent-session",
      lineage_role: "child",
    };
    const mirror: HookEvent = {
      ...event("mirror-session", "cursor"),
      origin_session_id: "parent-session",
      origin_platform: "claude",
      lineage_role: "mirror",
    };

    const indexes = buildTraceSessionIndexes([parent, child, mirror], [], [], []);

    expect(indexes.sessions).toHaveLength(1);
    expect(indexes.sessions[0]).toMatchObject({
      id: "parent-session",
      rawSessionIds: ["parent-session", "child-session", "mirror-session"],
      platforms: ["claude", "cursor", "opencode"],
      lineageConfidence: "explicit",
    });
    expect(indexes.sessions[0].childSessions?.map((session) => session.id)).toEqual(["child-session"]);
    expect(indexes.sessions[0].mirrorSessions?.map((session) => session.id)).toEqual(["mirror-session"]);
    expect(indexes.sessionGroups[0]).toMatchObject({
      id: "parent-session",
      rawSessionIds: ["parent-session", "child-session", "mirror-session"],
      lineageConfidence: "explicit",
    });
  });

  it("merges linked child evidence into grouped primary rows", () => {
    const parent = event("parent-session", "claude");
    const child: HookEvent = {
      ...event("child-session", "opencode"),
      timestamp: "2026-05-27T12:00:01.000Z",
      tool_name: "Edit",
      candidate_paths: ["/home/trav/repos/slopgate/src/child.py"],
      parent_session_id: "parent-session",
      root_session_id: "parent-session",
      lineage_role: "child",
    };
    const childFinding = finding("PY-CODE-013", "deny");
    childFinding.session_id = "child-session";
    childFinding.timestamp = "2026-05-27T12:00:02.000Z";
    const childResult: HookResult = {
      timestamp: "2026-05-27T12:00:03.000Z",
      platform: "opencode",
      event_name: "PostToolUse",
      session_id: "child-session",
      tool_name: "Edit",
      findings: [
        {
          rule_id: "PY-CODE-013",
          severity: "MEDIUM",
          decision: "deny",
          message: "blocked in child",
        },
      ],
      errors: null,
      output: null,
    };
    const childSubprocess: SubprocessRun = {
      timestamp: "2026-05-27T12:00:04.000Z",
      event_name: "PostToolUse",
      session_id: "child-session",
      command: "pytest tests/test_child.py",
      cwd: "/home/trav/repos/slopgate",
      returncode: 1,
      stdout: "",
      stderr: "failed",
      duration_ms: 50,
    };

    const indexes = buildTraceSessionIndexes([parent, child], [childFinding], [childResult], [childSubprocess]);

    expect(indexes.sessions).toHaveLength(1);
    expect(indexes.sessions[0]).toMatchObject({
      id: "parent-session",
      eventCount: 2,
      finalOutcome: "deny",
      pathCount: 1,
    });
    expect([...indexes.sessions[0].rawSessionIds].sort()).toEqual(["child-session", "parent-session"]);
    expect(indexes.sessions[0].tools).toEqual(["Bash", "Edit"]);
    expect(indexes.sessions[0].events.map((item) => item.session_id)).toEqual(["parent-session", "child-session"]);
    expect(indexes.sessions[0].findings.map((item) => item.session_id)).toEqual(["child-session"]);
    expect(indexes.sessions[0].results.map((item) => item.session_id)).toEqual(["child-session"]);
    expect(indexes.sessions[0].subprocesses.map((item) => item.session_id)).toEqual(["child-session"]);
  });

  it("infers mirrored historical sessions from matching windows and paths", () => {
    const opencodeMirror = [
      traceEvent("opencode-root", "2026-05-27T12:00:00.000Z", "opencode", ["/repo/dashboard/src/hooks/useTraceData.ts"]),
      traceEvent("opencode-root", "2026-05-27T12:03:00.000Z", "opencode", ["/repo/dashboard/src/components/SessionExplorer.tsx"], "Grep"),
    ];
    const claudeMirror = [
      traceEvent("legacy-claude-mirror", "2026-05-27T12:00:01.000Z", "claude", ["/repo/dashboard/src/hooks/useTraceData.ts"]),
      traceEvent(
        "legacy-claude-mirror",
        "2026-05-27T12:03:02.000Z",
        "claude",
        ["/repo/dashboard/src/components/SessionExplorer.tsx"],
        "Grep",
      ),
    ];
    const unrelated = [
      traceEvent("unrelated-claude-session", "2026-05-27T12:00:01.000Z", "claude", ["/repo/other/file.ts"]),
      traceEvent("unrelated-claude-session", "2026-05-27T12:03:02.000Z", "claude", ["/repo/other/file.ts"], "Grep"),
    ];

    const indexes = buildTraceSessionIndexes([...opencodeMirror, ...claudeMirror, ...unrelated], [], [], []);
    const grouped = indexes.sessions.find((session) => session.id === "opencode-root");
    const standalone = indexes.sessions.find((session) => session.id === "unrelated-claude-session");

    expect(indexes.sessions).toHaveLength(2);
    expect(grouped).toMatchObject({
      id: "opencode-root",
      lineageConfidence: "inferred",
      platforms: ["claude", "opencode"],
    });
    expect([...(grouped?.rawSessionIds ?? [])].sort()).toEqual(["legacy-claude-mirror", "opencode-root"]);
    expect(grouped?.mirrorSessions?.map((session) => session.id)).toEqual(["legacy-claude-mirror"]);
    expect(grouped?.childSessions).toEqual([]);
    expect(standalone).toMatchObject({
      id: "unrelated-claude-session",
      lineageConfidence: "none",
      rawSessionIds: ["unrelated-claude-session"],
    });
  });

  it("infers contained historical child sessions under non-claude parent rows", () => {
    const parentEvents = [
      traceEvent("opencode-parent", "2026-05-27T12:00:00.000Z", "opencode", ["/repo/dashboard/src/hooks/useTraceData.ts"]),
      traceEvent("opencode-parent", "2026-05-27T12:10:00.000Z", "opencode", ["/repo/dashboard/src/components/SessionExplorer.tsx"], "Grep"),
    ];
    const childEvents = [
      traceEvent("legacy-claude-child", "2026-05-27T12:02:00.000Z", "claude", ["/repo/dashboard/src/hooks/useTraceData.ts"]),
      traceEvent("legacy-claude-child", "2026-05-27T12:03:00.000Z", "claude", ["/repo/dashboard/src/hooks/useTraceData.ts"], "Grep"),
    ];
    const unrelatedEvents = [
      traceEvent("unrelated-contained-session", "2026-05-27T12:02:00.000Z", "claude", ["/repo/other/file.ts"]),
      traceEvent("unrelated-contained-session", "2026-05-27T12:03:00.000Z", "claude", ["/repo/other/file.ts"], "Grep"),
    ];

    const indexes = buildTraceSessionIndexes([...parentEvents, ...childEvents, ...unrelatedEvents], [], [], []);
    const grouped = indexes.sessions.find((session) => session.id === "opencode-parent");
    const standalone = indexes.sessions.find((session) => session.id === "unrelated-contained-session");

    expect(indexes.sessions).toHaveLength(2);
    expect(grouped).toMatchObject({
      id: "opencode-parent",
      lineageConfidence: "inferred",
      platforms: ["claude", "opencode"],
    });
    expect([...(grouped?.rawSessionIds ?? [])].sort()).toEqual(["legacy-claude-child", "opencode-parent"]);
    expect(grouped?.childSessions?.map((session) => session.id)).toEqual(["legacy-claude-child"]);
    expect(grouped?.mirrorSessions).toEqual([]);
    expect(standalone).toMatchObject({
      id: "unrelated-contained-session",
      lineageConfidence: "none",
      rawSessionIds: ["unrelated-contained-session"],
    });
  });
});
