import { act, render, screen, waitFor } from "@testing-library/react";
import { createElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TraceDataProvider, useTraceDataSource } from "./TraceDataContext";
import { classifyLine, coerceTraceRecord } from "./traceRecordValidation";

describe("live trace record validation", () => {
  it("accepts current result rows without event-only candidate metadata", () => {
    const result = {
      timestamp: "2026-05-13T08:56:50.795313+00:00",
      platform: "claude",
      event_name: "PostToolUse",
      session_id: "session-1",
      tool_name: "Bash",
      findings: [],
      errors: null,
      output: null,
      platform_capability: "full",
      enforcement_mode: "repo_strict",
      resolved_repo_root: "/workspace/example",
      degraded_reason: null,
    };

    expect(classifyLine(result)).toBe("result");
    expect(coerceTraceRecord(result)).toMatchObject({ type: "result", record: result });
  });

  it("accepts current rule finding rows without event-only candidate metadata", () => {
    const finding = {
      timestamp: "2026-05-13T08:56:50.371391+00:00",
      platform: "codex",
      event_name: "PreToolUse",
      session_id: "session-2",
      tool_name: "Write",
      rule_id: "QUALITY-LINT-001",
      severity: "HIGH",
      decision: "deny",
      message: "blocked",
      additional_context: null,
      metadata: {},
    };

    expect(classifyLine(finding)).toBe("rule");
    expect(coerceTraceRecord(finding)).toMatchObject({ type: "rule", record: finding });
  });

  it("ignores rules.jsonl metric rows instead of counting them as schema failures", () => {
    const metric = {
      timestamp: "2026-05-13T08:56:50.371391+00:00",
      rule_id: "engine.metrics",
      title: "rule engine timings",
      severity: "LOW",
      decision: null,
      ast_parses: 12,
      elapsed_ms: 4.2,
      enrichers_fired: 0,
    };

    expect(classifyLine(metric)).toBe("ignored");
    expect(coerceTraceRecord(metric)).toMatchObject({ type: "ignored" });
  });
});

class MockEventSource {
  static instances: MockEventSource[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((event: MessageEvent<string>) => void) | null = null;
  onerror: (() => void) | null = null;
  readonly url: string;

  constructor(url: string) {
    this.url = url;
    MockEventSource.instances.push(this);
  }

  close() {}

  emit(record: unknown) {
    this.onmessage?.(new MessageEvent("message", { data: JSON.stringify(record) }));
  }
}

function RuleCountProbe() {
  const { data } = useTraceDataSource();
  return createElement("div", { "data-testid": "rule-count" }, data.rules.length);
}

function streamRule(message: string, metadata: Record<string, unknown>) {
  return {
    timestamp: "2026-05-13T08:56:50.371391+00:00",
    platform: "claude",
    event_name: "PostToolUse",
    session_id: "same-session",
    tool_name: "Bash",
    rule_id: "QUALITY-LINT-001",
    severity: "HIGH",
    decision: "deny",
    message,
    additional_context: null,
    metadata,
  };
}

describe("TraceDataProvider stream de-duplication", () => {
  beforeEach(() => {
    MockEventSource.instances = [];
    vi.stubGlobal("EventSource", MockEventSource);
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: true,
      json: async () => ({
        ok: true,
        lookback_hours: 168,
        loaded_at: "2026-05-13T08:56:00.000Z",
        truncated: {},
        data: { events: [], rules: [], results: [], subprocesses: [] },
      }),
    })));
    Object.defineProperty(window, "__SLOPGATE_DATA__", {
      configurable: true,
      writable: true,
      value: { events: [], rules: [], results: [], subprocesses: [] },
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    Reflect.deleteProperty(window, "__SLOPGATE_DATA__");
  });

  it("keeps same-timestamp rule findings when message or metadata differs", async () => {
    render(createElement(TraceDataProvider, null, createElement(RuleCountProbe)));

    await waitFor(() => expect(MockEventSource.instances.length).toBeGreaterThan(0));
    const stream = MockEventSource.instances[0];
    act(() => {
      stream.emit(streamRule("first finding", { path: "src/a.py" }));
      stream.emit(streamRule("second finding", { path: "src/b.py" }));
    });

    await waitFor(() => expect(screen.getByTestId("rule-count")).toHaveTextContent("2"));
  });
});
