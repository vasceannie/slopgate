import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FlagProvider } from "@/context/FlagContext";
import { buildTraceSessionIndexes } from "@/hooks/useTraceData";
import {
	initialTimelineSelection,
	primarySessionCause,
	type SessionData,
	sessionActivitySummary,
	type TimelineEntry,
} from "../../lib/sessionHelpers";
import type { HookEvent, HookResult, LineageRole, Platform } from "@/types/slopgate";
import { SessionExplorer } from "./SessionExplorer";
import { SessionTimeline } from "./SessionTimeline";

function lineageEvent(input: {
	sessionId: string;
	timestamp: string;
	platform?: Platform;
	toolName?: string;
	candidatePaths?: string[];
	parentSessionId?: string;
	rootSessionId?: string;
	originSessionId?: string;
	lineageRole?: LineageRole;
}): HookEvent {
	const event: HookEvent = {
		timestamp: input.timestamp,
		platform: input.platform ?? "opencode",
		event_name: "PreToolUse",
		session_id: input.sessionId,
		tool_name: input.toolName ?? "Bash",
		candidate_paths: input.candidatePaths ?? ["/repo/src/lineage.py"],
		languages: ["python"],
	};
	if (input.parentSessionId) event.parent_session_id = input.parentSessionId;
	if (input.rootSessionId) event.root_session_id = input.rootSessionId;
	if (input.originSessionId) event.origin_session_id = input.originSessionId;
	if (input.lineageRole) event.lineage_role = input.lineageRole;
	return event;
}

function lineageResult(input: {
	sessionId: string;
	timestamp: string;
	platform?: Platform;
	toolName?: string;
	parentSessionId?: string;
	rootSessionId?: string;
	originSessionId?: string;
	lineageRole?: LineageRole;
}): HookResult {
	const result: HookResult = {
		timestamp: input.timestamp,
		platform: input.platform ?? "opencode",
		event_name: "PreToolUse",
		session_id: input.sessionId,
		tool_name: input.toolName ?? "Bash",
		findings: [
			{
				rule_id: "PY-CODE-012",
				severity: "MEDIUM",
				decision: "warn",
				message: "Child session produced this finding.",
			},
		],
		errors: [],
		output: null,
		skipped: false,
	};
	if (input.parentSessionId) result.parent_session_id = input.parentSessionId;
	if (input.rootSessionId) result.root_session_id = input.rootSessionId;
	if (input.originSessionId) result.origin_session_id = input.originSessionId;
	if (input.lineageRole) result.lineage_role = input.lineageRole;
	return result;
}

function requiredParentElement(element: Element): HTMLElement {
	const parent = element.parentElement;
	if (!parent) {
		throw new Error("Expected test target to have a parent element.");
	}
	return parent;
}

function textContentMatch(pattern: RegExp) {
	return (_content: string, node: Element | null) => {
		const hasText = (element: Element | null) =>
			pattern.test(element?.textContent || "");
		return (
			hasText(node) &&
			Array.from(node?.children ?? []).every((child) => !hasText(child))
		);
	};
}

const editSession: SessionData = {
    id: "opencode-edit-session",
    platform: "opencode",
    eventCount: 2,
    tools: ["Edit"],
    languages: ["python"],
    pathCount: 1,
    finalOutcome: "allow",
    duration: 1,
    events: [
        {
            timestamp: "2026-06-11T22:11:36.000Z",
            platform: "opencode",
            event_name: "PreToolUse",
            session_id: "opencode-edit-session",
            tool_name: "Edit",
            candidate_paths: ["/repo/src/slopgate/engine/_evaluation.py"],
            languages: ["python"],
            tool_input: {
                file_path: "/repo/src/slopgate/engine/_evaluation.py",
                old_string: "return {'tool_input': None}",
                new_string: "return {'tool_input': ctx.tool_input}",
            },
        },
    ],
    findings: [],
    results: [
        {
            timestamp: "2026-06-11T22:11:36.250Z",
            platform: "opencode",
            event_name: "PreToolUse",
            session_id: "opencode-edit-session",
            tool_name: "Edit",
            findings: [],
            errors: [],
            output: null,
            skipped: false,
        },
    ],
    subprocesses: [],
};

describe("SessionTimeline", () => {
    function renderTimeline(session: SessionData) {
        render(
            <FlagProvider>
                <SessionTimeline session={session} />
            </FlagProvider>,
        );
    }

	it("surfaces child and mirror origins inside a grouped parent timeline", () => {
		const childEvent = lineageEvent({
			sessionId: "child-session-beta",
			timestamp: "2026-06-12T10:00:10.000Z",
			parentSessionId: "parent-session-alpha",
			rootSessionId: "parent-session-alpha",
			lineageRole: "child",
			toolName: "Bash",
		});
		const mirrorEvent = lineageEvent({
			sessionId: "mirror-session-gamma",
			timestamp: "2026-06-12T10:00:20.000Z",
			platform: "cursor",
			originSessionId: "parent-session-alpha",
			lineageRole: "mirror",
			toolName: "Edit",
		});
		const childMirrorEvent = lineageEvent({
			sessionId: "child-mirror-session-delta",
			timestamp: "2026-06-12T10:00:30.000Z",
			platform: "cursor",
			parentSessionId: "parent-session-alpha",
			rootSessionId: "parent-session-alpha",
			originSessionId: "parent-session-alpha",
			lineageRole: "child_mirror",
			toolName: "Write",
		});
		const { sessions } = buildTraceSessionIndexes(
			[
				lineageEvent({
					sessionId: "parent-session-alpha",
					timestamp: "2026-06-12T10:00:00.000Z",
					platform: "claude",
					lineageRole: "parent",
					toolName: "Read",
				}),
				childEvent,
				mirrorEvent,
				childMirrorEvent,
			],
			[],
			[
				lineageResult({
					sessionId: "child-session-beta",
					timestamp: "2026-06-12T10:00:11.000Z",
					parentSessionId: "parent-session-alpha",
					rootSessionId: "parent-session-alpha",
					lineageRole: "child",
					toolName: "Bash",
				}),
				lineageResult({
					sessionId: "mirror-session-gamma",
					timestamp: "2026-06-12T10:00:21.000Z",
					platform: "cursor",
					originSessionId: "parent-session-alpha",
					lineageRole: "mirror",
					toolName: "Edit",
				}),
				lineageResult({
					sessionId: "child-mirror-session-delta",
					timestamp: "2026-06-12T10:00:31.000Z",
					platform: "cursor",
					parentSessionId: "parent-session-alpha",
					rootSessionId: "parent-session-alpha",
					originSessionId: "parent-session-alpha",
					lineageRole: "child_mirror",
					toolName: "Write",
				}),
			],
			[],
		);

		render(
			<FlagProvider>
				<SessionExplorer sessions={sessions} />
			</FlagProvider>,
		);

		expect(screen.getByText("parent-session-a…")).toBeInTheDocument();
		expect(screen.queryByText("child-session-b…")).not.toBeInTheDocument();
		expect(screen.queryByText("mirror-session-g…")).not.toBeInTheDocument();

		fireEvent.click(screen.getByText("parent-session-a…"));

		expect(screen.getByText("+3 linked")).toBeInTheDocument();
		expect(screen.getByText("4 grouped sessions")).toBeInTheDocument();
		expect(screen.getByText("1 child")).toBeInTheDocument();
		expect(screen.getByText("1 mirror")).toBeInTheDocument();
		expect(screen.getByText("1 child + mirror")).toBeInTheDocument();
		expect(screen.queryByText(/source child:/)).not.toBeInTheDocument();
		expect(screen.queryByText(/source mirror:/)).not.toBeInTheDocument();
		expect(screen.queryByText("Source session")).not.toBeInTheDocument();
	});

	it("renders unioned parent child and mirror trace fixture data in the component UI", () => {
		const traceEvents: HookEvent[] = [
			{
				timestamp: "2026-06-12T10:00:00.000Z",
				platform: "claude",
				event_name: "PreToolUse",
				session_id: "parent-union-session-alpha",
				tool_name: "Read",
				candidate_paths: ["/repo/README.md"],
				languages: ["markdown"],
				lineage_role: "parent",
			},
			{
				timestamp: "2026-06-12T10:00:10.000Z",
				platform: "opencode",
				event_name: "PreToolUse",
				session_id: "child-union-session-beta",
				tool_name: "Bash",
				candidate_paths: ["/repo/src/child.py"],
				languages: ["python"],
				command: "pytest child.py",
				parent_session_id: "parent-union-session-alpha",
				root_session_id: "parent-union-session-alpha",
				lineage_role: "child",
			},
			{
				timestamp: "2026-06-12T10:00:20.000Z",
				platform: "cursor",
				event_name: "PreToolUse",
				session_id: "mirror-union-session-gamma",
				tool_name: "Edit",
				candidate_paths: ["/repo/dashboard/mirror.ts"],
				languages: ["typescript"],
				origin_session_id: "parent-union-session-alpha",
				lineage_role: "mirror",
			},
			{
				timestamp: "2026-06-12T10:00:30.000Z",
				platform: "cursor",
				event_name: "PreToolUse",
				session_id: "child-mirror-union-session-delta",
				tool_name: "Write",
				candidate_paths: ["/repo/crates/delta.rs"],
				languages: ["rust"],
				parent_session_id: "parent-union-session-alpha",
				root_session_id: "parent-union-session-alpha",
				origin_session_id: "parent-union-session-alpha",
				lineage_role: "child_mirror",
			},
			{
				timestamp: "2026-06-12T10:01:00.000Z",
				platform: "opencode",
				event_name: "PreToolUse",
				session_id: "standalone-control-session-epsilon",
				tool_name: "Read",
				candidate_paths: ["/repo/docs/unrelated.md"],
				languages: ["markdown"],
				lineage_role: "raw",
			},
		];
		const traceResults: HookResult[] = [
			{
				timestamp: "2026-06-12T10:00:11.000Z",
				platform: "opencode",
				event_name: "PreToolUse",
				session_id: "child-union-session-beta",
				tool_name: "Bash",
				findings: [
					{
						rule_id: "PY-CODE-012",
						severity: "MEDIUM",
						decision: "warn",
						message: "Child warning should merge into the parent.",
					},
				],
				errors: [],
				output: null,
				skipped: false,
				parent_session_id: "parent-union-session-alpha",
				root_session_id: "parent-union-session-alpha",
				lineage_role: "child",
			},
			{
				timestamp: "2026-06-12T10:00:21.000Z",
				platform: "cursor",
				event_name: "PreToolUse",
				session_id: "mirror-union-session-gamma",
				tool_name: "Edit",
				findings: [
					{
						rule_id: "TS-CODE-001",
						severity: "LOW",
						decision: "warn",
						message: "Mirror warning should merge into the parent.",
					},
				],
				errors: [],
				output: null,
				skipped: false,
				origin_session_id: "parent-union-session-alpha",
				lineage_role: "mirror",
			},
			{
				timestamp: "2026-06-12T10:00:31.000Z",
				platform: "cursor",
				event_name: "PreToolUse",
				session_id: "child-mirror-union-session-delta",
				tool_name: "Write",
				findings: [
					{
						rule_id: "RS-CODE-001",
						severity: "MEDIUM",
						decision: "deny",
						message: "Child mirror denial should control parent outcome.",
					},
				],
				errors: [],
				output: null,
				skipped: false,
				parent_session_id: "parent-union-session-alpha",
				root_session_id: "parent-union-session-alpha",
				origin_session_id: "parent-union-session-alpha",
				lineage_role: "child_mirror",
			},
		];
		const { sessions } = buildTraceSessionIndexes(
			traceEvents,
			[],
			traceResults,
			[],
		);

		render(
			<FlagProvider>
				<SessionExplorer sessions={sessions} />
			</FlagProvider>,
		);

		expect(screen.getByText("parent-union-ses…")).toBeInTheDocument();
		expect(screen.getByText(/standalone-contr/)).toBeInTheDocument();
		expect(screen.queryByText("child-union-ses…")).not.toBeInTheDocument();
		expect(screen.getByText("deny")).toBeInTheDocument();
		expect(screen.getByText("claude")).toBeInTheDocument();
		expect(screen.getByText("cursor")).toBeInTheDocument();
		expect(screen.getAllByText("opencode").length).toBeGreaterThan(0);
		expect(screen.getByText("Write")).toBeInTheDocument();
		expect(screen.getAllByText("+3").length).toBeGreaterThan(0);
		expect(screen.getByText("delta.rs")).toBeInTheDocument();
		expect(screen.getByText("31s")).toBeInTheDocument();

		fireEvent.click(screen.getByText("parent-union-ses…"));

		expect(screen.getByText("+3 linked")).toBeInTheDocument();
		expect(screen.getByText("Blocked Session")).toBeInTheDocument();
		expect(screen.getByText("Write (+3)")).toBeInTheDocument();
		expect(screen.getByText("Events:")).toBeInTheDocument();
		expect(screen.getByText("4")).toBeInTheDocument();
		expect(screen.getByText("4 grouped sessions")).toBeInTheDocument();
		expect(screen.getByText("1 child")).toBeInTheDocument();
		expect(screen.getByText("1 mirror")).toBeInTheDocument();
		expect(screen.getByText("1 child + mirror")).toBeInTheDocument();
		expect(screen.queryByText(/source child:/)).not.toBeInTheDocument();
		expect(screen.queryByText(/source mirror:/)).not.toBeInTheDocument();
		expect(
			screen.getByText("Child mirror denial should control parent outcome."),
		).toBeInTheDocument();

		fireEvent.change(screen.getByPlaceholderText("Search sessions..."), {
			target: { value: "mirror.ts" },
		});
		expect(screen.getByText("parent-union-ses…")).toBeInTheDocument();
		expect(screen.queryByText(/standalone-contr/)).not.toBeInTheDocument();

		const languageFilter = requiredParentElement(screen.getByText("Language:"));
		fireEvent.click(within(languageFilter).getByRole("button", { name: "All" }));
		expect(screen.getByText("markdown")).toBeInTheDocument();
		expect(screen.getByText("python")).toBeInTheDocument();
		expect(screen.getByText("rust")).toBeInTheDocument();
		expect(screen.getByText("typescript")).toBeInTheDocument();
	});

	it("renders inferred historical mirror grouping in the component UI", () => {
		const { sessions } = buildTraceSessionIndexes(
			[
				lineageEvent({
					sessionId: "opencode-inferred-root",
					timestamp: "2026-06-12T11:00:00.000Z",
					platform: "opencode",
					candidatePaths: ["/repo/dashboard/src/hooks/useTraceData.ts"],
					toolName: "Read",
				}),
				lineageEvent({
					sessionId: "opencode-inferred-root",
					timestamp: "2026-06-12T11:03:00.000Z",
					platform: "opencode",
					candidatePaths: ["/repo/dashboard/src/components/SessionExplorer.tsx"],
					toolName: "Grep",
				}),
				lineageEvent({
					sessionId: "legacy-claude-mirror",
					timestamp: "2026-06-12T11:00:01.000Z",
					platform: "claude",
					candidatePaths: ["/repo/dashboard/src/hooks/useTraceData.ts"],
					toolName: "Read",
				}),
				lineageEvent({
					sessionId: "legacy-claude-mirror",
					timestamp: "2026-06-12T11:03:02.000Z",
					platform: "claude",
					candidatePaths: ["/repo/dashboard/src/components/SessionExplorer.tsx"],
					toolName: "Grep",
				}),
				lineageEvent({
					sessionId: "standalone-inferred-control",
					timestamp: "2026-06-12T11:00:01.000Z",
					platform: "claude",
					candidatePaths: ["/repo/unrelated/file.ts"],
					toolName: "Read",
				}),
				lineageEvent({
					sessionId: "standalone-inferred-control",
					timestamp: "2026-06-12T11:03:02.000Z",
					platform: "claude",
					candidatePaths: ["/repo/unrelated/file.ts"],
					toolName: "Grep",
				}),
			],
			[],
			[],
			[],
		);

		render(
			<FlagProvider>
				<SessionExplorer sessions={sessions} />
			</FlagProvider>,
		);

		expect(screen.getByText("opencode-inferre…")).toBeInTheDocument();
		expect(screen.getByText(/standalone-infer/)).toBeInTheDocument();
		expect(screen.queryByText("legacy-claude-m…")).not.toBeInTheDocument();
		expect(screen.getByText("+1 linked")).toBeInTheDocument();

		fireEvent.click(screen.getByText("opencode-inferre…"));

		expect(screen.getByText("inferred")).toBeInTheDocument();
		expect(screen.getByText("2 grouped sessions")).toBeInTheDocument();
		expect(screen.getByText("1 mirror")).toBeInTheDocument();
		expect(screen.queryByText("mirror: legacy-claude-mirror")).not.toBeInTheDocument();
		expect(screen.queryByText(/source mirror:/)).not.toBeInTheDocument();

		fireEvent.change(screen.getByPlaceholderText("Search sessions..."), {
			target: { value: "SessionExplorer.tsx" },
		});
		expect(screen.getByText("opencode-inferre…")).toBeInTheDocument();
		expect(screen.queryByText(/standalone-infer/)).not.toBeInTheDocument();
	});

	    it("shows edit diffs and raw tool input in expanded hook drilldown", () => {
        renderTimeline(editSession);

        fireEvent.click(
            screen.getByRole("button", { name: /hook pretooluse/i }),
        );

        expect(
            screen.getAllByText("Patch / focused diff:")[0],
        ).toBeInTheDocument();
        expect(screen.getAllByText("Tool input:")[0]).toBeInTheDocument();
        expect(
            screen.getAllByText(
                /\/repo\/src\/slopgate\/engine\/_evaluation\.py/,
            ).length,
        ).toBeGreaterThan(0);
        expect(
            screen.getAllByText(/-return \{'tool_input': None\}/)[0],
        ).toBeInTheDocument();
        expect(
            screen.getAllByText(
                /\+return \{'tool_input': ctx\.tool_input\}/,
            )[0],
        ).toBeInTheDocument();
        expect(screen.getAllByText("old_string")[0]).toBeInTheDocument();
        expect(screen.getAllByText("new_string")[0]).toBeInTheDocument();
    });

    it("carries pre-tool code into later post-tool rows", () => {
        renderTimeline({
            ...editSession,
            id: "opencode-post-edit-session",
            events: [
                {
                    timestamp: "2026-06-11T22:11:20.000Z",
                    platform: "opencode",
                    event_name: "PreToolUse",
                    session_id: "opencode-post-edit-session",
                    tool_name: "apply_patch",
                    candidate_paths: [
                        "/repo/dashboard/src/components/SessionTimeline.tsx",
                    ],
                    languages: ["typescript"],
                    tool_input: {
                        patchText: [
                            "*** Begin Patch",
                            "*** Update File: dashboard/src/components/SessionTimeline.tsx",
                            "-old",
                            "+new",
                            "*** End Patch",
                        ].join("\n"),
                    },
                },
            ],
            results: [
                {
                    timestamp: "2026-06-11T22:11:29.000Z",
                    platform: "opencode",
                    event_name: "PostToolUse",
                    session_id: "opencode-post-edit-session",
                    tool_name: "apply_patch",
                    findings: [],
                    errors: [],
                    output: null,
                    skipped: false,
                },
            ],
        });

        fireEvent.click(screen.getByRole("button", { name: /result: allow/i }));

        expect(
            screen.getAllByText("Patch / focused diff:")[0],
        ).toBeInTheDocument();
        expect(
            screen.getAllByText(
                "diff --git a/dashboard/src/components/SessionTimeline.tsx b/dashboard/src/components/SessionTimeline.tsx",
            )[0],
        ).toBeInTheDocument();
        expect(
            screen.getAllByText(
                "--- a/dashboard/src/components/SessionTimeline.tsx",
            )[0],
        ).toBeInTheDocument();
        expect(
            screen.getAllByText(
                "+++ b/dashboard/src/components/SessionTimeline.tsx",
            )[0],
        ).toBeInTheDocument();
        expect(screen.getAllByText(/\+new/).length).toBeGreaterThan(0);
        expect(screen.getAllByText("Tool input:")[0]).toBeInTheDocument();
        expect(screen.getAllByText("patchText")[0]).toBeInTheDocument();
        expect(
            screen.getAllByText(/Captured apply_patch body/)[0],
        ).toBeInTheDocument();

        fireEvent.click(
            screen.getAllByRole("button", {
                name: /Patch \/ focused diff raw view/i,
            })[0],
        );
        expect(
            screen.getAllByText(/\*\*\* Begin Patch/)[0],
        ).toBeInTheDocument();

        fireEvent.click(
            screen.getAllByRole("button", { name: /Tool input raw view/i })[0],
        );
        expect(screen.getAllByText('"patchText"')[0]).toBeInTheDocument();
    });

    it("shows patch bodies carried directly on result rows", () => {
        renderTimeline({
            ...editSession,
            id: "opencode-result-patch-session",
            events: [],
            results: [
                {
                    timestamp: "2026-06-11T22:11:29.000Z",
                    platform: "opencode",
                    event_name: "PreToolUse",
                    session_id: "opencode-result-patch-session",
                    tool_name: "apply_patch",
                    findings: [],
                    errors: [],
                    output: null,
                    skipped: false,
                    tool_input: {
                        patchText: [
                            "*** Begin Patch",
                            "*** Update File: dashboard/src/components/SessionTimeline.tsx",
                            "-old",
                            "+new",
                            "*** End Patch",
                        ].join("\n"),
                    },
                },
            ],
        });

        fireEvent.click(screen.getByRole("button", { name: /result: allow/i }));

        expect(
            screen.getAllByText("Patch / focused diff:")[0],
        ).toBeInTheDocument();
        expect(
            screen.getAllByText(
                "diff --git a/dashboard/src/components/SessionTimeline.tsx b/dashboard/src/components/SessionTimeline.tsx",
            )[0],
        ).toBeInTheDocument();
        expect(screen.getAllByText(/\+new/).length).toBeGreaterThan(0);
        expect(screen.getAllByText("Tool input:")[0]).toBeInTheDocument();
        expect(screen.getAllByText("patchText")[0]).toBeInTheDocument();
    });

    it("beautifies generic tool input aliases while keeping raw JSON available", () => {
        renderTimeline({
            ...editSession,
            id: "generic-input-output-session",
            events: [],
            results: [
                {
                    timestamp: "2026-06-11T22:14:00.000Z",
                    platform: "codex",
                    event_name: "PreToolUse",
                    session_id: "generic-input-output-session",
                    tool_name: "Bash",
                    findings: [],
                    errors: [],
                    output: {
                        tool_args: {
                            command: "uv run pytest tests/test_dashboard.py -q",
                            path: "tests/test_dashboard.py",
                            nested: { adapter: "codex" },
                        },
                    },
                    skipped: false,
                },
            ],
        });

        fireEvent.click(screen.getByRole("button", { name: /result: allow/i }));

        expect(screen.getAllByText("Tool input:")[0]).toBeInTheDocument();
        expect(screen.getAllByText("command")[0]).toBeInTheDocument();
        expect(screen.getAllByText("path")[0]).toBeInTheDocument();
        expect(screen.getAllByText("nested")[0]).toBeInTheDocument();
        expect(
            screen.getAllByText(/uv run pytest tests\/test_dashboard\.py -q/)
                .length,
        ).toBeGreaterThan(0);

        fireEvent.click(
            screen.getAllByRole("button", { name: /Tool input raw view/i })[0],
        );
        expect(screen.getAllByText('"nested"')[0]).toBeInTheDocument();
    });

    it("preserves direct url-only tool payloads in pretty and raw views", () => {
        renderTimeline({
            ...editSession,
            id: "url-only-tool-session",
            events: [],
            results: [
                {
                    timestamp: "2026-06-11T22:15:00.000Z",
                    platform: "claude",
                    event_name: "PreToolUse",
                    session_id: "url-only-tool-session",
                    tool_name: "WebFetch",
                    findings: [],
                    errors: [],
                    output: {
                        url: "https://docs.example.test/reference",
                    },
                    skipped: false,
                },
            ],
        });

        fireEvent.click(screen.getByRole("button", { name: /result: allow/i }));

        expect(screen.getAllByText("Tool input:")[0]).toBeInTheDocument();
        expect(screen.getAllByText("url")[0]).toBeInTheDocument();
        expect(
            screen.getAllByText("https://docs.example.test/reference").length,
        ).toBeGreaterThan(0);

        fireEvent.click(
            screen.getAllByRole("button", { name: /Tool input raw view/i })[0],
        );
        expect(screen.getAllByText('"url"')[0]).toBeInTheDocument();
    });
    it("explains when historical apply_patch traces lack captured body content", () => {
        renderTimeline({
            ...editSession,
            id: "opencode-historical-patch-session",
            events: [
                {
                    timestamp: "2026-06-11T20:56:27.580Z",
                    platform: "opencode",
                    event_name: "PreToolUse",
                    session_id: "opencode-historical-patch-session",
                    tool_name: "apply_patch",
                    candidate_paths: [
                        "/repo/dashboard/scripts/build_standalone/__init__.pyi",
                    ],
                    languages: ["python"],
                },
            ],
            results: [
                {
                    timestamp: "2026-06-11T20:56:27.597Z",
                    platform: "opencode",
                    event_name: "PreToolUse",
                    session_id: "opencode-historical-patch-session",
                    tool_name: "apply_patch",
                    findings: [
                        {
                            rule_id: "PY-IMPORT-001",
                            severity: "LOW",
                            decision: "context",
                            message:
                                "/repo/dashboard/scripts/build_standalone/__init__.pyi imports 6 names from coercion.",
                            additional_context: null,
                        },
                    ],
                    errors: [],
                    output: null,
                    skipped: false,
                },
            ],
        });

        fireEvent.click(
            screen.getByRole("button", { name: /hook pretooluse/i }),
        );

        expect(
            screen.getAllByText("Tool input unavailable")[0],
        ).toBeInTheDocument();
        expect(
            screen.getAllByText(/Tool call body was not captured/)[0],
        ).toBeInTheDocument();
        expect(
            screen.getAllByText("Grouped finding(s):")[0],
        ).toBeInTheDocument();
        expect(screen.queryAllByText("Patch / focused diff:").length).toBe(0);
    });

    it("renders finding additional context as formatted evidence code", () => {
        renderTimeline({
            ...editSession,
            id: "finding-evidence-session",
            events: [],
            results: [
                {
                    timestamp: "2026-06-11T22:12:00.000Z",
                    platform: "codex",
                    event_name: "UserPromptSubmit",
                    session_id: "finding-evidence-session",
                    tool_name: null,
                    findings: [
                        {
                            rule_id: "BUILTIN-INJECT-PROMPT",
                            severity: "LOW",
                            decision: "context",
                            message: "No message provided.",
                            additional_context:
                                "{\"policy\":\"deterministic\",\"nested\":{\"language\":\"json\"}}",
                        },
                        {
                            rule_id: "PY-CODE-012",
                            severity: "LOW",
                            decision: "context",
                            message: "Python evidence.",
                            additional_context: "def choose_policy(value):\n    return value",
                        },
                    ],
                    errors: [],
                    output: null,
                    skipped: false,
                },
            ],
        });

        expect(screen.getAllByText("Evidence (JSON):").length).toBeGreaterThan(0);
        expect(screen.getAllByText("Evidence (Python):").length).toBeGreaterThan(0);
        expect(
            screen.getAllByText(textContentMatch(/"policy": "deterministic"/))
                .length,
        ).toBeGreaterThan(0);
        expect(
            screen.getAllByText(textContentMatch(/def choose_policy\(value\):/))
                .length,
        ).toBeGreaterThan(0);
    });

    it("formats Claude hookSpecificOutput context instead of raw JSON", () => {
        renderTimeline({
            ...editSession,
            id: "claude-output-session",
            platform: "claude",
            events: [],
            results: [
                {
                    timestamp: "2026-06-11T22:12:00.000Z",
                    platform: "claude",
                    event_name: "PreToolUse",
                    session_id: "claude-output-session",
                    tool_name: "Bash",
                    findings: [],
                    errors: [],
                    output: {
                        hookSpecificOutput: {
                            hookEventName: "PreToolUse",
                            permissionDecision: "deny",
                            permissionDecisionReason:
                                "[PY-CODE-012 | LOW] move logic",
                            additionalContext: [
                                "[PY-CODE-012 | LOW] first advisory",
                                "[PY-IMPORT-001 | LOW] second advisory",
                            ].join("\n"),
                        },
                        additional_context: "[PY-TEST-005 | LOW] root advisory",
                    },
                    skipped: false,
                },
            ],
        });

        fireEvent.click(screen.getByRole("button", { name: /result: allow/i }));

        expect(
            screen.getAllByText("Permission decision")[0],
        ).toBeInTheDocument();
        expect(screen.getAllByText("Permission reason")[0]).toBeInTheDocument();
        expect(
            screen.getAllByText("Additional context").length,
        ).toBeGreaterThan(0);
		expect(
			screen.getAllByText((_content, node) => {
				const hasText = (n: Element | null) =>
					/\[PY-CODE-012 \| LOW\] first advisory/.test(
						n.textContent || "",
					);
				return (
					hasText(node) &&
					Array.from(node?.children ?? []).every((c) => !hasText(c))
				);
			})[0],
		).toBeInTheDocument();
		expect(
			screen.getAllByText((_content, node) => {
				const hasText = (n: Element | null) =>
					/\[PY-IMPORT-001 \| LOW\] second advisory/.test(
						n.textContent || "",
					);
				return (
					hasText(node) &&
					Array.from(node?.children ?? []).every((c) => !hasText(c))
				);
			})[0],
		).toBeInTheDocument();
		expect(
			screen.getAllByText((_content, node) => {
				const hasText = (n: Element | null) =>
					/\[PY-TEST-005 \| LOW\] root advisory/.test(
						n.textContent || "",
					);
				return (
					hasText(node) &&
					Array.from(node?.children ?? []).every((c) => !hasText(c))
				);
			})[0],
        ).toBeInTheDocument();

        fireEvent.click(
            screen.getAllByRole("button", { name: /Output raw view/i })[0],
        );
        expect(
            screen.getAllByText('"hookSpecificOutput"')[0],
        ).toBeInTheDocument();
    });

    it("formats Codex and OpenCode output keys", () => {
        renderTimeline({
            ...editSession,
            id: "mixed-output-session",
            events: [],
            results: [
                {
                    timestamp: "2026-06-11T22:13:00.000Z",
                    platform: "codex",
                    event_name: "PostToolUse",
                    session_id: "mixed-output-session",
                    tool_name: "Bash",
                    findings: [],
                    errors: [],
                    output: {
                        continue: false,
                        stopReason: "[CRITICAL | CRITICAL] stop now",
                    },
                    skipped: false,
                },
                {
                    timestamp: "2026-06-11T22:12:00.000Z",
                    platform: "opencode",
                    event_name: "PostToolUse",
                    session_id: "mixed-output-session",
                    tool_name: "Bash",
                    findings: [],
                    errors: [],
                    output: {
                        action: "context",
                        context: "[PY-CODE-012 | LOW] advisory text",
                    },
                    skipped: false,
                },
            ],
        });

        fireEvent.click(
            screen.getAllByRole("button", { name: /result: allow/i })[0],
        );
        expect(screen.getAllByText("Continue")[0]).toBeInTheDocument();
        expect(screen.getAllByText("Stop reason")[0]).toBeInTheDocument();

        fireEvent.click(
            screen.getAllByRole("button", { name: /result: allow/i })[1],
        );
        expect(screen.getAllByText("Action")[0]).toBeInTheDocument();
        expect(screen.getAllByText("Context")[0]).toBeInTheDocument();
    });

    it("allows clearing all filters in one click and shows active filter summary", () => {
        renderTimeline({
            ...editSession,
            results: [
                {
                    timestamp: "2026-06-11T22:11:29.000Z",
                    platform: "opencode",
                    event_name: "PreToolUse",
                    session_id: "opencode-edit-session",
                    tool_name: "Edit",
                    findings: [
                        {
                            rule_id: "PY-CODE-012",
                            severity: "MEDIUM",
                            decision: "warn",
                            message: "Avoid long blocks",
                        },
                    ],
                    errors: null,
                    output: null,
                },
            ],
        });

        // Trigger details Toggle: findings
        const findingsToggle = screen.getByRole("button", {
            name: "Has findings",
        });
        fireEvent.click(findingsToggle);

        // The active filter summary should show
        expect(screen.getByText(/Active Filters:/)).toBeInTheDocument();
        expect(screen.getAllByText("Has findings")[0]).toBeInTheDocument();

        // Clear filters
        const clearBtn = screen.getByRole("button", {
            name: /Clear timeline filters/i,
        });
        fireEvent.click(clearBtn);

        // Active filter summary should be gone
        expect(screen.queryByText(/Active Filters:/)).not.toBeInTheDocument();
    });

    it("closes menus and flag panels on Escape key and returns focus to their triggers", () => {
        renderTimeline(editSession);

        // 1. Open Event filter menu
        const eventFilterTrigger = screen.getAllByRole("button", {
            name: "All",
        })[0];
        fireEvent.click(eventFilterTrigger);

        // Expect Options dropdown is visible
        expect(screen.getByText("Options")).toBeInTheDocument();

        // Press Escape
        fireEvent.keyDown(window, { key: "Escape" });

        // Menu should close
        expect(screen.queryByText("Options")).not.toBeInTheDocument();

        // 2. Open flag panel on a row
        fireEvent.click(
            screen.getByRole("button", { name: /hook pretooluse/i }),
        );
        const flagBtn = screen.getAllByRole("button", { name: /flag/i })[0];
        fireEvent.click(flagBtn);

        // Expect Flag for Investigation panel is visible
        expect(screen.getByText("Flag for Investigation")).toBeInTheDocument();

        // Press Escape
        fireEvent.keyDown(window, { key: "Escape" });

        // Panel should close
        expect(
            screen.queryByText("Flag for Investigation"),
        ).not.toBeInTheDocument();
    });
});

describe("SessionExplorer", () => {
    it("filters sessions by search query (matching ID, platform, rule, path, command)", () => {
        const sessions: SessionData[] = [
            {
                id: "first-session-id-bash",
                platform: "opencode",
                eventCount: 1,
                tools: ["Bash"],
                languages: ["python"],
                pathCount: 1,
                finalOutcome: "allow",
                duration: 5000,
                events: [
                    {
                        timestamp: "2026-06-11T22:11:36.000Z",
                        platform: "opencode",
                        event_name: "PreToolUse",
                        session_id: "first-session-id-bash",
                        tool_name: "Bash",
                        command: "pytest tests/test_explorer.py",
                        candidate_paths: ["/repo/src/engine.py"],
                        languages: ["python"],
                    },
                ],
                findings: [],
                results: [],
                subprocesses: [],
            },
            {
                id: "second-session-id-edit",
                platform: "claude",
                eventCount: 1,
                tools: ["Edit"],
                languages: ["typescript"],
                pathCount: 1,
                finalOutcome: "deny",
                duration: 2000,
                events: [],
                findings: [
                    {
                        timestamp: "2026-06-12T10:00:06.000Z",
                        platform: "claude",
                        event_name: "PreToolUse",
                        session_id: "second-session-id-edit",
                        tool_name: "Edit",
                        rule_id: "PY-IMPORT-001",
                        severity: "MEDIUM",
                        decision: "deny",
                        message: "imports 6 names",
                        additional_context: null,
                        metadata: {},
                    },
                ],
                results: [],
                subprocesses: [],
            },
        ];

        render(
            <FlagProvider>
                <SessionExplorer sessions={sessions} />
            </FlagProvider>,
        );

        // Initially both sessions are displayed
        expect(screen.getByText("first-session-id…")).toBeInTheDocument();
        expect(screen.getByText("second-session-i…")).toBeInTheDocument();

        // Search for "claude" (platform)
        const searchInput = screen.getByPlaceholderText("Search sessions...");
        fireEvent.change(searchInput, { target: { value: "claude" } });

        expect(screen.queryByText("first-session-id…")).not.toBeInTheDocument();
        expect(screen.getByText("second-session-i…")).toBeInTheDocument();

        // Search for "pytest" (command)
        fireEvent.change(searchInput, { target: { value: "pytest" } });
        expect(screen.getByText("first-session-id…")).toBeInTheDocument();
        expect(screen.queryByText("second-session-i…")).not.toBeInTheDocument();

        // Search for "PY-IMPORT-001" (rule ID)
        fireEvent.change(searchInput, { target: { value: "PY-IMPORT-001" } });
        expect(screen.queryByText("first-session-id…")).not.toBeInTheDocument();
        expect(screen.getByText("second-session-i…")).toBeInTheDocument();
    });

	it("shows lineage links and searches linked child sessions", () => {
		const sessions: SessionData[] = [
			{
				...editSession,
				id: "parent-session-alpha",
				platform: "claude",
				platforms: ["claude", "cursor", "opencode"],
				rawSessionIds: [
					"parent-session-alpha",
					"child-session-beta",
					"mirror-session-gamma",
				],
				lineageConfidence: "explicit",
				lineageRole: "parent",
				childSessions: [
					{
						...editSession,
						id: "child-session-beta",
						platform: "opencode",
						parentSessionId: "parent-session-alpha",
						lineageRole: "child",
					},
				],
				mirrorSessions: [
					{
						...editSession,
						id: "mirror-session-gamma",
						platform: "cursor",
						originSessionId: "parent-session-alpha",
						lineageRole: "mirror",
					},
				],
			},
		];

		render(
			<FlagProvider>
				<SessionExplorer sessions={sessions} />
			</FlagProvider>,
		);

		expect(screen.getByText("+2 linked")).toBeInTheDocument();
		expect(screen.getByText("claude")).toBeInTheDocument();
		expect(screen.getByText("cursor")).toBeInTheDocument();
		expect(screen.getByText("opencode")).toBeInTheDocument();

		fireEvent.click(screen.getByText("parent-session-a…"));

		expect(screen.getByText("explicit")).toBeInTheDocument();
		expect(screen.getByText("3 grouped sessions")).toBeInTheDocument();
		expect(screen.getByText("1 child")).toBeInTheDocument();
		expect(screen.getByText("1 mirror")).toBeInTheDocument();

		fireEvent.change(screen.getByPlaceholderText("Search sessions..."), {
			target: { value: "child-session-beta" },
		});

		expect(screen.getByText("parent-session-a…")).toBeInTheDocument();
	});

	it("counts child_mirror linked sessions once in lineage details", () => {
		const childMirrorSession: SessionData = {
			...editSession,
			id: "child-mirror-session-beta",
			platform: "cursor",
			parentSessionId: "parent-session-alpha",
			originSessionId: "parent-session-alpha",
			lineageRole: "child_mirror",
		};
		const sessions: SessionData[] = [
			{
				...editSession,
				id: "parent-session-alpha",
				platform: "claude",
				platforms: ["claude", "cursor"],
				rawSessionIds: ["parent-session-alpha", "child-mirror-session-beta"],
				lineageConfidence: "explicit",
				lineageRole: "parent",
				childSessions: [childMirrorSession],
				mirrorSessions: [childMirrorSession],
			},
		];

		render(
			<FlagProvider>
				<SessionExplorer sessions={sessions} />
			</FlagProvider>,
		);

		expect(screen.getByText("+1 linked")).toBeInTheDocument();

		fireEvent.click(screen.getByText("parent-session-a…"));

		expect(screen.getByText("2 grouped sessions")).toBeInTheDocument();
		expect(screen.getByText("1 child + mirror")).toBeInTheDocument();
		expect(
			screen.queryByText("mirror: child-mirror-session-beta"),
		).not.toBeInTheDocument();
		expect(
			screen.queryByText("child + mirror: child-mirror-session-beta"),
		).not.toBeInTheDocument();
		expect(
			screen.queryByText("unclassified: child-mirror-session-beta"),
		).not.toBeInTheDocument();
		expect(
			screen.queryByText("raw: child-mirror-session-beta"),
		).not.toBeInTheDocument();
	});
});

describe("sessionHelpers", () => {
    const sampleSession: SessionData = {
        id: "test-session-id",
        platform: "claude",
        eventCount: 2,
        tools: ["Read", "Edit"],
        languages: ["typescript"],
        pathCount: 2,
        finalOutcome: "allow",
        duration: 12000,
        events: [
            {
                timestamp: "2026-06-12T10:00:00.000Z",
                platform: "claude",
                event_name: "PreToolUse",
                session_id: "test-session-id",
                tool_name: "Read",
                candidate_paths: ["src/index.ts"],
                languages: ["typescript"],
            },
            {
                timestamp: "2026-06-12T10:00:05.000Z",
                platform: "claude",
                event_name: "PreToolUse",
                session_id: "test-session-id",
                tool_name: "Edit",
                candidate_paths: ["src/main.ts"],
                languages: ["typescript"],
            },
        ],
        findings: [
            {
                timestamp: "2026-06-12T10:00:06.000Z",
                platform: "claude",
                event_name: "PreToolUse",
                session_id: "test-session-id",
                tool_name: "Edit",
                rule_id: "PY-CODE-012",
                severity: "MEDIUM",
                decision: "warn",
                message: "Avoid long blocks",
                additional_context: null,
                metadata: {},
            },
        ],
        results: [
            {
                timestamp: "2026-06-12T10:00:07.000Z",
                platform: "claude",
                event_name: "PreToolUse",
                session_id: "test-session-id",
                tool_name: "Edit",
                findings: [
                    {
                        rule_id: "PY-CODE-013",
                        severity: "HIGH",
                        decision: "deny",
                        message: "Do not exceed limits",
                    },
                ],
                errors: null,
                output: null,
            },
        ],
        subprocesses: [],
    };

    it("primarySessionCause selects the highest priority blocking finding", () => {
        const cause = primarySessionCause(sampleSession);
        expect(cause.decision).toBe("deny");
        expect(cause.ruleId).toBe("PY-CODE-013");
        expect(cause.severity).toBe("HIGH");
    });

    it("primarySessionCause returns Clean allow if outcome is allow and no findings", () => {
        const cleanSession: SessionData = {
            ...sampleSession,
            findings: [],
            results: [],
            finalOutcome: "allow",
        };
        const cause = primarySessionCause(cleanSession);
        expect(cause.decision).toBe("allow");
        expect(cause.message).toBe("Clean allow");
    });

    it("sessionActivitySummary returns last tool and tool/event counts", () => {
        const summary = sessionActivitySummary(sampleSession);
        expect(summary.lastTool).toBe("Edit");
        expect(summary.toolCount).toBe(2);
        expect(summary.eventCount).toBe(2);
    });

    it("initialTimelineSelection prefers blocking row", () => {
        const entries: TimelineEntry[] = [
            {
                id: "e1",
                type: "event",
                decision: "allow",
                label: "",
                detail: "",
                sessionId: "",
                flagItemType: "event",
                flagItemId: "",
                flagLabel: "",
                time: "",
            },
            {
                id: "e2",
                type: "result",
                decision: "deny",
                findingCount: 1,
                label: "",
                detail: "",
                sessionId: "",
                flagItemType: "result",
                flagItemId: "",
                flagLabel: "",
                time: "",
            },
            {
                id: "e3",
                type: "hook",
                decision: "allow",
                label: "",
                detail: "",
                sessionId: "",
                flagItemType: "result",
                flagItemId: "",
                flagLabel: "",
                time: "",
            },
        ];
        const selection = initialTimelineSelection(entries);
        expect(selection).toBe("e2");
    });
});
