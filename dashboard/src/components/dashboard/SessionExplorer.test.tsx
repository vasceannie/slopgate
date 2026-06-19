import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { SessionData } from "@/lib/sessionHelpers";
import { SessionExplorer } from "./SessionExplorer";
import { calculateScrollAdjustment, determineAnchor, findFirstVisibleRow } from "./sessionExplorerAnchoring";

vi.mock("./FlagButton", () => ({
  FlagButton: () => <button type="button">flag</button>,
}));

function session(overrides: Partial<SessionData> = {}): SessionData {
  return {
    id: "ses_139b33e35ffefMrhqJH9yU5J2R",
    title: null,
    platform: "codex",
    platforms: ["codex"],
    eventCount: 0,
    tools: [],
    languages: [],
    pathCount: 0,
    finalOutcome: "allow",
    duration: 0,
    events: [],
    findings: [],
    results: [],
    subprocesses: [],
    ...overrides,
  };
}

function event(overrides: Partial<SessionData["events"][number]> = {}): SessionData["events"][number] {
  return {
    timestamp: "2026-06-14T12:00:00Z",
    platform: "codex",
    event_name: "PreToolUse",
    session_id: "ses_139b33e35ffefMrhqJH9yU5J2R",
    tool_name: "bash",
    candidate_paths: [],
    languages: [],
    ...overrides,
  };
}

function mockHtmlElement(overrides: Partial<HTMLElement>): HTMLElement {
  return overrides as HTMLElement;
}

function mockTableSectionElement(overrides: Partial<HTMLTableSectionElement>): HTMLTableSectionElement {
  return overrides as HTMLTableSectionElement;
}

describe("SessionExplorer", () => {
  it("uses session title as the primary session label when available", () => {
    render(
      <SessionExplorer
        sessions={[
          session({
            title: "Fix dashboard session labels",
          }),
        ]}
      />,
    );

    expect(screen.getByText("Fix dashboard session labels")).toBeInTheDocument();
    expect(screen.queryByText("ses_139b33e35ffe…")).not.toBeInTheDocument();
  });

  it("falls back to the shortened session id when no title exists", () => {
    render(<SessionExplorer sessions={[session()]} />);

    expect(screen.getByText("ses_139b33e35ffe…")).toBeInTheDocument();
  });

  it("matches native OpenCode and secondary identities in search", () => {
    render(
      <SessionExplorer
        sessions={[
          session({
            id: "opencode-plugin-synthetic",
            title: "Fix dashboard session labels",
            platform: "opencode",
            platforms: ["opencode"],
            secondaryIds: ["opencode-plugin-synthetic"],
            nativeSessionIds: {
              opencode: "ses_139981ae7ffeOKOMbswUJdo3Oy",
            },
          }),
          session({
            id: "unrelated-session",
            title: "Unrelated dashboard work",
          }),
        ]}
      />,
    );

    fireEvent.change(screen.getByPlaceholderText("Search sessions..."), {
      target: { value: "ses_139981ae7ffe" },
    });

    expect(screen.getByText("Fix dashboard session labels")).toBeInTheDocument();
    expect(screen.queryByText("Unrelated dashboard work")).not.toBeInTheDocument();
  });

  it("renders first path and +N paths correctly in collapsed row, and does not show full paths list directly", () => {
    const s = session({
      id: "ses_path_test",
      events: [
        event({
          candidate_paths: ["/src/a.ts", "/src/b.ts", "/src/c.ts", "/src/d.ts"],
        }),
      ],
    });
    render(<SessionExplorer sessions={[s]} />);
    expect(screen.getByText("a.ts")).toBeInTheDocument();
    expect(screen.getByText("+3")).toBeInTheDocument();
    expect(screen.queryByText("b.ts")).not.toBeInTheDocument();
  });

  it("renders multi-platform session with first platform and +N", () => {
    const s = session({
      id: "ses_plat_test",
      platforms: ["claude", "codex", "cursor"],
    });
    render(<SessionExplorer sessions={[s]} />);
    expect(screen.getByText("claude")).toBeInTheDocument();
    expect(screen.getByText("+2")).toBeInTheDocument();
    expect(screen.queryByText("codex")).not.toBeInTheDocument();
  });

  it("renders tool names with +N count", () => {
    const s = session({
      id: "ses_tool_test",
      events: [
        event({ timestamp: "2026-06-14T12:00:00Z", tool_name: "bash" }),
        event({ timestamp: "2026-06-14T12:01:00Z", tool_name: "read" }),
        event({ timestamp: "2026-06-14T12:02:00Z", tool_name: "write" }),
      ],
    });
    render(<SessionExplorer sessions={[s]} />);
    expect(screen.getByText("write")).toBeInTheDocument();
    expect(screen.getByText("+2")).toBeInTheDocument();
    expect(screen.queryByText("bash")).not.toBeInTheDocument();
  });

  it("keeps expanded session expanded after a rerender with new records", () => {
    const s1 = session({
      id: "ses_expand_test_1",
      childSessions: [session({ id: "child_1" })],
    });
    const { rerender } = render(<SessionExplorer sessions={[s1]} />);

    const row = screen.getByText("ses_expand_test_…");
    fireEvent.click(row);
    expect(screen.getByText("Lineage")).toBeInTheDocument();

    const s2 = { ...s1, duration: 5000 };
    const s3 = session({ id: "ses_expand_test_2" });
    rerender(<SessionExplorer sessions={[s2, s3]} />);

    expect(screen.getByText("Lineage")).toBeInTheDocument();
  });

  it("explicit user actions reset paging/expansion and skip anchoring", () => {
    const s1 = session({
      id: "ses_user_act_1",
      childSessions: [session({ id: "child_1" })],
    });
    const s2 = session({
      id: "ses_user_act_2",
      childSessions: [session({ id: "child_2" })],
    });
    render(<SessionExplorer sessions={[s1, s2]} />);

    const row = screen.getByText("ses_user_act_1…");
    fireEvent.click(row);
    expect(screen.getByText("Lineage")).toBeInTheDocument();

    const searchInput = screen.getByPlaceholderText("Search sessions...");
    fireEvent.change(searchInput, { target: { value: "user_act" } });

    expect(screen.queryByText("Lineage")).not.toBeInTheDocument();
  });

  it("new or updated sessions receive the subtle update marker/class; unchanged sessions do not", () => {
    const s1 = session({ id: "ses_unchanged", duration: 1000 });
    const s2 = session({ id: "ses_updated", duration: 2000 });
    const { container, rerender } = render(<SessionExplorer sessions={[s1, s2]} />);

    expect(container.querySelector(".session-row-updated")).toBeNull();

    const s2Updated = { ...s2, duration: 3000 };
    const s3 = session({ id: "ses_new", duration: 4000 });
    rerender(<SessionExplorer sessions={[s1, s2Updated, s3]} />);

    const s1Row = container.querySelector('tr[data-session-id="ses_unchanged"]');
    const s2Row = container.querySelector('tr[data-session-id="ses_updated"]');
    const s3Row = container.querySelector('tr[data-session-id="ses_new"]');

    expect(s1Row?.classList.contains("session-row-updated")).toBe(false);
    expect(s2Row?.classList.contains("session-row-updated")).toBe(true);
    expect(s3Row?.classList.contains("session-row-updated")).toBe(true);
  });
});

describe("Viewport anchoring helpers", () => {
  beforeEach(() => {
    vi.stubGlobal("scrollBy", vi.fn());
    vi.stubGlobal("innerHeight", 1000);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("findFirstVisibleRow finds the first row intersecting the viewport", () => {
    const mockRow1 = mockHtmlElement({
      getBoundingClientRect: () => ({ top: -10, bottom: 30 }) as DOMRect,
      getAttribute: () => "ses_1",
    });
    const mockRow2 = mockHtmlElement({
      getBoundingClientRect: () => ({ top: 10, bottom: 50 }) as DOMRect,
      getAttribute: () => "ses_2",
    });

    const tableBody = mockTableSectionElement({
      querySelectorAll: () => [mockRow1, mockRow2] as unknown as NodeListOf<Element>,
    });

    const result = findFirstVisibleRow(tableBody);
    expect(result).toBe(mockRow1);
  });

  it("determineAnchor prefers expanded session", () => {
    const mockExpanded = mockHtmlElement({
      getBoundingClientRect: () => ({ top: 100, bottom: 140 }) as DOMRect,
      getAttribute: () => "ses_expanded",
    });

    const tableBody = mockTableSectionElement({
      querySelector: (selector: string) => {
        if (selector === 'tr[data-session-id="ses_expanded"]') return mockExpanded;
        return null;
      },
      querySelectorAll: () => [] as unknown as NodeListOf<Element>,
    });

    const anchor = determineAnchor({ expanded: "ses_expanded", tableBody });
    expect(anchor?.id).toBe("ses_expanded");
    expect(anchor?.top).toBe(100);
  });

  it("determineAnchor falls back to first visible row if expanded is missing", () => {
    const mockVisible = mockHtmlElement({
      getBoundingClientRect: () => ({ top: 200, bottom: 240 }) as DOMRect,
      getAttribute: (attr: string) => (attr === "data-session-id" ? "ses_visible" : null),
    });

    const tableBody = mockTableSectionElement({
      querySelector: () => null,
      querySelectorAll: () => [mockVisible] as unknown as NodeListOf<Element>,
    });

    const anchor = determineAnchor({ expanded: "ses_missing", tableBody });
    expect(anchor?.id).toBe("ses_visible");
    expect(anchor?.top).toBe(200);
  });

  it("calculateScrollAdjustment returns delta if conditions are met", () => {
    const mockNewEl = mockHtmlElement({
      getBoundingClientRect: () => ({ top: 150, bottom: 190 }) as DOMRect,
    });

    const tableBody = mockTableSectionElement({
      querySelector: () => mockNewEl,
    });

    const delta = calculateScrollAdjustment("ses_1", 100, tableBody, 100);
    expect(delta).toBe(50);
  });

  it("calculateScrollAdjustment returns 0 if scrollY is near top", () => {
    const mockNewEl = mockHtmlElement({
      getBoundingClientRect: () => ({ top: 150, bottom: 190 }) as DOMRect,
    });

    const tableBody = mockTableSectionElement({
      querySelector: () => mockNewEl,
    });

    const delta = calculateScrollAdjustment("ses_1", 100, tableBody, 10);
    expect(delta).toBe(0);
  });

  it("calculateScrollAdjustment returns 0 if missing anchor row", () => {
    const tableBody = mockTableSectionElement({
      querySelector: () => null,
    });

    const delta = calculateScrollAdjustment("ses_missing", 100, tableBody, 100);
    expect(delta).toBe(0);
  });
});
