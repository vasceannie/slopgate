import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { FlagProvider } from "@/context/FlagContext";
import type { SessionData } from "./SessionExplorer";
import { SessionTimeline } from "./SessionTimeline";

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

	it("shows edit diffs and raw tool input in expanded hook drilldown", () => {
		renderTimeline(editSession);

		fireEvent.click(screen.getByRole("button", { name: /hook pretooluse/i }));

		expect(screen.getByText("Patch / focused diff:")).toBeInTheDocument();
		expect(screen.getByText("Tool input:")).toBeInTheDocument();
		expect(
			screen.getAllByText(/\/repo\/src\/slopgate\/engine\/_evaluation\.py/)
				.length,
		).toBeGreaterThan(0);
		expect(
			screen.getByText(/-return \{'tool_input': None\}/),
		).toBeInTheDocument();
		expect(
			screen.getByText(/\+return \{'tool_input': ctx\.tool_input\}/),
		).toBeInTheDocument();
		expect(screen.getByText(/"old_string"/)).toBeInTheDocument();
		expect(screen.getByText(/"new_string"/)).toBeInTheDocument();
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
						patchText:
							"*** Begin Patch\n*** Update File: dashboard/src/components/SessionTimeline.tsx\n-old\n+new\n*** End Patch",
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

		expect(screen.getByText("Patch / focused diff:")).toBeInTheDocument();
		expect(screen.getAllByText(/\*\*\* Begin Patch/).length).toBeGreaterThan(0);
		expect(screen.getAllByText(/\+new/).length).toBeGreaterThan(0);
		expect(screen.getByText("Tool input:")).toBeInTheDocument();
		expect(screen.getByText(/"patchText"/)).toBeInTheDocument();
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
						patchText:
							"*** Begin Patch\n*** Update File: dashboard/src/components/SessionTimeline.tsx\n-old\n+new\n*** End Patch",
					},
				},
			],
		});

		fireEvent.click(screen.getByRole("button", { name: /result: allow/i }));

		expect(screen.getByText("Patch / focused diff:")).toBeInTheDocument();
		expect(screen.getAllByText(/\*\*\* Begin Patch/).length).toBeGreaterThan(0);
		expect(screen.getAllByText(/\+new/).length).toBeGreaterThan(0);
		expect(screen.getByText("Tool input:")).toBeInTheDocument();
		expect(screen.getByText(/"patchText"/)).toBeInTheDocument();
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

		fireEvent.click(screen.getByRole("button", { name: /hook pretooluse/i }));

		expect(screen.getByText("Tool input unavailable")).toBeInTheDocument();
		expect(
			screen.getByText(/Tool call body was not captured/),
		).toBeInTheDocument();
		expect(screen.getByText("Grouped finding(s):")).toBeInTheDocument();
		expect(screen.queryByText("Patch / focused diff:")).not.toBeInTheDocument();
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
							permissionDecisionReason: "[PY-CODE-012 | LOW] move logic",
							additionalContext:
								"[PY-CODE-012 | LOW] first advisory\n[PY-IMPORT-001 | LOW] second advisory",
						},
						additional_context: "[PY-TEST-005 | LOW] root advisory",
					},
					skipped: false,
				},
			],
		});

		fireEvent.click(screen.getByRole("button", { name: /result: allow/i }));

		expect(screen.getByText("Permission decision")).toBeInTheDocument();
		expect(screen.getByText("Permission reason")).toBeInTheDocument();
		expect(screen.getAllByText("Additional context").length).toBeGreaterThan(0);
		expect(
			screen.getByText(/\[PY-CODE-012 \| LOW\] first advisory/),
		).toBeInTheDocument();
		expect(
			screen.getByText(/\[PY-IMPORT-001 \| LOW\] second advisory/),
		).toBeInTheDocument();
		expect(
			screen.getByText(/\[PY-TEST-005 \| LOW\] root advisory/),
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
		expect(screen.getByText("Continue")).toBeInTheDocument();
		expect(screen.getByText("Stop reason")).toBeInTheDocument();

		fireEvent.click(
			screen.getAllByRole("button", { name: /result: allow/i })[1],
		);
		expect(screen.getByText("Action")).toBeInTheDocument();
		expect(screen.getByText("Context")).toBeInTheDocument();
	});
});
