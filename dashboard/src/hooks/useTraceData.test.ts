import { describe, expect, it } from "vitest";
import type {
	HookEvent,
	HookResult,
	Platform,
	RuleFinding,
	SubprocessRun,
} from "@/types/slopgate";
import {
	buildTraceSessionIndexes,
	streamSchemaValidationWarning,
	summarizeTopRules,
} from "./useTraceData";

function finding(
	rule_id: string,
	decision: RuleFinding["decision"],
): RuleFinding {
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

		expect(topRules.map((rule) => rule.rule_id)).toEqual([
			"PY-CODE-018",
			"PY-CODE-013",
			"ENRICHMENT",
			"_ENRICHMENT_METRICS",
		]);
		expect(
			topRules.find((rule) => rule.rule_id === "ENRICHMENT"),
		).toMatchObject({ count: 3, decisions: { context: 3 } });
		expect(
			topRules.find((rule) => rule.rule_id === "_ENRICHMENT_METRICS"),
		).toMatchObject({ count: 1, decisions: { info: 1 } });
	});

	it("preserves raw advisory telemetry when no enforcement findings exist", () => {
		const rules = [
			finding("ENRICHMENT", "context"),
			finding("PY-CODE-012", "context"),
			finding("PY-CODE-012", "context"),
			finding("_ENRICHMENT_METRICS", "info"),
		];

		const topRules = summarizeTopRules(rules);

		expect(topRules.map((rule) => rule.rule_id)).toEqual([
			"PY-CODE-012",
			"ENRICHMENT",
			"_ENRICHMENT_METRICS",
		]);
		expect(topRules).toHaveLength(3);
	});

	it("keeps high-volume advisory rules available after enforcement-heavy sorting", () => {
		const rules = Array.from({ length: 26 }, (_unused, index) =>
			finding(`PY-BLOCK-${index}`, "deny"),
		);
		rules.push(
			...Array.from({ length: 50 }, () =>
				finding("ADVISORY-HOTSPOT", "context"),
			),
		);

		const topRules = summarizeTopRules(rules);

		expect(
			topRules.find((rule) => rule.rule_id === "ADVISORY-HOTSPOT"),
		).toMatchObject({
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
		expect(streamSchemaValidationWarning(2, 0)).toBe(
			"2 streamed records failed dashboard schema validation.",
		);
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
				candidate_paths: [
					"/home/trav/repos/slopgate/src/a.py",
					"/home/trav/repos/slopgate/src/a.py",
				],
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

		const indexes = buildTraceSessionIndexes(
			events,
			rules,
			results,
			subprocesses,
		);

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

		const indexes = buildTraceSessionIndexes(
			[parent, child, mirror],
			[],
			[],
			[],
		);

		expect(indexes.sessions).toHaveLength(1);
		expect(indexes.sessions[0]).toMatchObject({
			id: "parent-session",
			rawSessionIds: ["parent-session", "child-session", "mirror-session"],
			platforms: ["claude", "cursor", "opencode"],
			lineageConfidence: "explicit",
		});
		expect(indexes.sessions[0].childSessions?.map((session) => session.id)).toEqual([
			"child-session",
		]);
		expect(indexes.sessions[0].mirrorSessions?.map((session) => session.id)).toEqual([
			"mirror-session",
		]);
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

		const indexes = buildTraceSessionIndexes(
			[parent, child],
			[childFinding],
			[childResult],
			[childSubprocess],
		);

		expect(indexes.sessions).toHaveLength(1);
	expect(indexes.sessions[0]).toMatchObject({
		id: "parent-session",
		eventCount: 2,
		finalOutcome: "deny",
		pathCount: 1,
	});
	expect([...indexes.sessions[0].rawSessionIds].sort()).toEqual([
		"child-session",
		"parent-session",
	]);
		expect(indexes.sessions[0].tools).toEqual(["Bash", "Edit"]);
		expect(indexes.sessions[0].events.map((item) => item.session_id)).toEqual([
			"parent-session",
			"child-session",
		]);
		expect(indexes.sessions[0].findings.map((item) => item.session_id)).toEqual([
			"child-session",
		]);
		expect(indexes.sessions[0].results.map((item) => item.session_id)).toEqual([
			"child-session",
		]);
		expect(indexes.sessions[0].subprocesses.map((item) => item.session_id)).toEqual([
			"child-session",
		]);
	});
});
