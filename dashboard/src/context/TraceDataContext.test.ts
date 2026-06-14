import {
	act,
	fireEvent,
	render,
	screen,
	waitFor,
} from "@testing-library/react";
import { createElement, useEffect, useRef, useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EVENT_NAMES } from "@/types/slopgate";
import { TraceDataProvider } from "./TraceDataContext";
import { classifyLine, coerceTraceRecord } from "./traceRecordValidation";
import { useTraceDataSource } from "./useTraceDataSource";

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
		expect(coerceTraceRecord(result)).toMatchObject({
			type: "result",
			record: result,
		});
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
		expect(coerceTraceRecord(finding)).toMatchObject({
			type: "rule",
			record: finding,
		});
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

	it("accepts raw subprocess records without duration_ms field", () => {
		const sub = {
			timestamp: "2026-06-04T22:45:27.405373+00:00",
			event_name: "PostToolUse",
			session_id: "sub-1",
			command: "python -m pytest -q tests/quality",
			cwd: "/home/trav/repos/example",
			returncode: 127,
			stdout: "",
			stderr: "not found",
		};

		expect(classifyLine(sub)).toBe("subprocess");
		const coerced = coerceTraceRecord(sub);
		expect(coerced).not.toBeNull();
		expect(coerced).toMatchObject({ type: "subprocess" });
		if (coerced?.type === "subprocess") {
			expect(coerced.record.duration_ms).toBe(0);
		}
	});

	it("normalizes raw lifecycle event rows from the live stream", () => {
		const rawEvent = {
			timestamp: "2026-06-11T02:02:33.860998+00:00",
			event_name: "Stop",
			session_id: "session-raw-event",
		};

		expect(classifyLine(rawEvent)).toBe("event");
		expect(coerceTraceRecord(rawEvent)).toMatchObject({
			type: "event",
			record: {
				platform: "unknown",
				platform_source: "unknown",
				tool_name: "",
				candidate_paths: [],
				languages: [],
			},
		});
	});

	it.each(EVENT_NAMES)(
		"accepts canonical platform event %s",
		(eventName) => {
			const rawEvent = {
				timestamp: "2026-06-11T02:02:33.860998+00:00",
				event_name: eventName,
				session_id: `session-${eventName}`,
			};

			expect(coerceTraceRecord(rawEvent)).toMatchObject({
				type: "event",
				record: {
					event_name: eventName,
					platform: "unknown",
					platform_source: "unknown",
					tool_name: "",
					candidate_paths: [],
					languages: [],
				},
			});
		},
	);

	it("preserves raw tool input on live event rows", () => {
		const rawEvent = {
			timestamp: "2026-06-11T02:02:33.860998+00:00",
			event_name: "PreToolUse",
			session_id: "session-raw-edit-event",
			tool_name: "Edit",
			tool_input: {
				file_path: "/workspace/example/src/app.ts",
				old_string: "const before = true;",
				new_string: "const after = true;",
			},
		};

		expect(coerceTraceRecord(rawEvent)).toMatchObject({
			type: "event",
			record: {
				tool_input: rawEvent.tool_input,
			},
		});
	});

	it("preserves aliased tool input from live event rows", () => {
		const rawEvent = {
			timestamp: "2026-06-11T02:02:33.860998+00:00",
			event_name: "PreToolUse",
			session_id: "session-raw-patch-event",
			tool_name: "apply_patch",
			tool_args: {
				patchText:
					"*** Begin Patch\n*** Update File: app.py\n-print(1)\n+print(2)\n*** End Patch",
			},
		};

		expect(coerceTraceRecord(rawEvent)).toMatchObject({
			type: "event",
			record: {
				tool_input: rawEvent.tool_args,
			},
		});
	});

	it("preserves tool input on normalized result rows", () => {
		const rawResult = {
			timestamp: "2026-06-11T02:02:33.860998+00:00",
			event_name: "PreToolUse",
			session_id: "session-result-patch-input",
			tool_name: "apply_patch",
			findings: [],
			tool_input: {
				patchText:
					"*** Begin Patch\n*** Update File: app.py\n-print(1)\n+print(2)\n*** End Patch",
			},
		};

		expect(coerceTraceRecord(rawResult)).toMatchObject({
			type: "result",
			record: {
				tool_input: rawResult.tool_input,
			},
		});
	});

	it("normalizes raw result rows from the live stream", () => {
		const rawResult = {
			timestamp: "2026-06-11T02:02:33.860998+00:00",
			event_name: "Stop",
			session_id: "session-raw-result",
			findings: [],
		};

		expect(classifyLine(rawResult)).toBe("result");
		expect(coerceTraceRecord(rawResult)).toMatchObject({
			type: "result",
			record: {
				platform: "unknown",
				platform_source: "unknown",
				tool_name: "",
				errors: [],
				output: null,
			},
		});
	});

	it("normalizes cursor platform and lineage aliases from live rows", () => {
		const rawEvent = {
			timestamp: "2026-06-11T02:02:33.860998+00:00",
			platform: "cursor",
			event_name: "PreToolUse",
			session_id: "cursor-child-session",
			parentSessionId: "parent-session",
			rootSessionID: "root-session",
			originPlatform: "claude",
			originSessionID: "origin-session",
			platformSource: "explicit",
			subagentType: "explore",
			spawnDescription: "Find session lineage",
			lineageRole: "child_mirror",
		};

		expect(coerceTraceRecord(rawEvent)).toMatchObject({
			type: "event",
			record: {
				platform: "cursor",
				parent_session_id: "parent-session",
				root_session_id: "root-session",
				origin_platform: "claude",
				origin_session_id: "origin-session",
				platform_source: "explicit",
				subagent_type: "explore",
				spawn_description: "Find session lineage",
				lineage_role: "child_mirror",
			},
		});
	});

	it("normalizes event session title aliases from live rows", () => {
		const rawEvent = {
			timestamp: "2026-06-11T02:02:33.860998+00:00",
			event_name: "SessionStart",
			session_id: "session-with-title",
			title: "Fix dashboard session labels",
		};

		expect(coerceTraceRecord(rawEvent)).toMatchObject({
			type: "event",
			record: {
				session_title: "Fix dashboard session labels",
			},
		});
	});

	it("preserves raw tool input on normalized result rows", () => {
		const rawResult = {
			timestamp: "2026-06-11T02:02:33.860998+00:00",
			event_name: "PreToolUse",
			session_id: "session-result-patch",
			tool_name: "apply_patch",
			findings: [],
			tool_input: {
				patchText:
					"*** Begin Patch\n*** Update File: app.py\n-print(1)\n+print(2)\n*** End Patch",
			},
		};

		expect(coerceTraceRecord(rawResult)).toMatchObject({
			type: "result",
			record: {
				tool_input: rawResult.tool_input,
			},
		});
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
		this.onmessage?.(
			new MessageEvent("message", { data: JSON.stringify(record) }),
		);
	}
}

const EMPTY_TRACE_RESPONSE = {
	ok: true,
	lookback_hours: 168,
	loaded_at: "2026-05-13T08:56:00.000Z",
	truncated: {},
	data: { events: [], rules: [], results: [], subprocesses: [] },
};

function RuleCountProbe() {
	const { data } = useTraceDataSource();
	return createElement(
		"div",
		{ "data-testid": "rule-count" },
		data.rules.length,
	);
}

function DataIdentityProbe() {
	const { data } = useTraceDataSource();
	const lastDataRef = useRef(data);
	const [dataChanges, setDataChanges] = useState(0);
	useEffect(() => {
		if (lastDataRef.current === data) return;
		lastDataRef.current = data;
		setDataChanges((count) => count + 1);
	}, [data]);
	return createElement(
		"div",
		{ "data-testid": "data-identity" },
		`${data.rules.length}:${dataChanges}`,
	);
}

function SourceStateProbe() {
	const { data, sourceMode, sourceMeta } = useTraceDataSource();
	return createElement(
		"div",
		{ "data-testid": "source-state" },
		`${sourceMode}:${sourceMeta.isSnapshotLoading}:${data.rules.length}:${data.events.length}:${sourceMeta.rejectedStreamRecords}`,
	);
}

function SnapshotSummaryProbe() {
	const { sourceMeta } = useTraceDataSource();
	return createElement(
		"div",
		{ "data-testid": "snapshot-summary" },
		JSON.stringify(sourceMeta.snapshotSummary ?? null),
	);
}

function SourceActionProbe() {
	const { data, ingestFiles, resetToMock, sourceMode, sourceMeta } =
		useTraceDataSource();
	return createElement(
		"div",
		null,
		createElement(
			"div",
			{ "data-testid": "source-state" },
			`${sourceMode}:${sourceMeta.isSnapshotLoading}:${data.rules.length}:${data.events.length}:${sourceMeta.rejectedStreamRecords}`,
		),
		createElement(
			"button",
			{ "data-testid": "reset", onClick: resetToMock, type: "button" },
			"reset",
		),
		createElement(
			"button",
			{
				"data-testid": "upload",
				onClick: () => {
					const uploadText = JSON.stringify(
						streamRule("uploaded finding", { path: "src/uploaded.py" }),
					);
					const upload = new File([uploadText], "rules.jsonl");
					Object.defineProperty(upload, "text", {
						value: async () => uploadText,
					});
					void ingestFiles([upload]);
				},
				type: "button",
			},
			"upload",
		),
	);
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
		vi.stubGlobal(
			"fetch",
			vi.fn(async () => ({
				ok: true,
				json: async () => EMPTY_TRACE_RESPONSE,
			})),
		);
		Reflect.deleteProperty(window, "__SLOPGATE_DATA__");
	});

	afterEach(() => {
		vi.unstubAllGlobals();
		Reflect.deleteProperty(window, "__SLOPGATE_DATA__");
	});

	it("keeps same-timestamp rule findings when message or metadata differs", async () => {
		render(
			createElement(TraceDataProvider, null, createElement(RuleCountProbe)),
		);

		await waitFor(() =>
			expect(MockEventSource.instances.length).toBeGreaterThan(0),
		);
		const stream = MockEventSource.instances[0];
		act(() => {
			stream.emit(streamRule("first finding", { path: "src/a.py" }));
			stream.emit(streamRule("second finding", { path: "src/b.py" }));
		});

		await waitFor(() =>
			expect(screen.getByTestId("rule-count")).toHaveTextContent("2"),
		);
	});

	it("ignores exact duplicate stream records", async () => {
		render(
			createElement(TraceDataProvider, null, createElement(RuleCountProbe)),
		);

		await waitFor(() =>
			expect(MockEventSource.instances.length).toBeGreaterThan(0),
		);
		const stream = MockEventSource.instances[0];
		const duplicate = streamRule("same finding", { path: "src/a.py" });
		act(() => {
			stream.emit(duplicate);
			stream.emit(duplicate);
		});

		await waitFor(() =>
			expect(screen.getByTestId("rule-count")).toHaveTextContent("1"),
		);
	});

	it("keeps trace data identity stable for exact duplicate stream records", async () => {
		render(
			createElement(TraceDataProvider, null, createElement(DataIdentityProbe)),
		);

		await waitFor(() =>
			expect(MockEventSource.instances.length).toBeGreaterThan(0),
		);
		const stream = MockEventSource.instances[0];
		const duplicate = streamRule("same finding", { path: "src/a.py" });
		act(() => {
			stream.emit(duplicate);
		});

		await waitFor(() =>
			expect(screen.getByTestId("data-identity")).toHaveTextContent(/^1:/),
		);
		const afterFirstRecord = screen.getByTestId("data-identity").textContent;
		expect(afterFirstRecord).toMatch(/^1:\d+$/);

		act(() => {
			stream.emit(duplicate);
		});

		expect(screen.getByTestId("data-identity").textContent).toBe(
			afterFirstRecord,
		);
	});

	it("ignores non-trace stream JSON without counting schema failures", async () => {
		render(
			createElement(TraceDataProvider, null, createElement(SourceStateProbe)),
		);

		await waitFor(() =>
			expect(MockEventSource.instances.length).toBeGreaterThan(0),
		);
		const stream = MockEventSource.instances[0];
		act(() => {
			stream.emit({ type: "heartbeat", ok: true });
			stream.emit(streamRule("accepted finding", { path: "src/a.py" }));
		});

		await waitFor(() =>
			expect(screen.getByTestId("source-state")).toHaveTextContent(
				"streaming:false:1:0:0",
			),
		);
	});
});

describe("TraceDataProvider initial snapshot loading", () => {
	beforeEach(() => {
		MockEventSource.instances = [];
		vi.stubGlobal("EventSource", MockEventSource);
		Reflect.deleteProperty(window, "__SLOPGATE_DATA__");
	});

	afterEach(() => {
		vi.unstubAllGlobals();
		Reflect.deleteProperty(window, "__SLOPGATE_DATA__");
	});

	it("requests a bounded 24h snapshot on initial load", async () => {
		const fetchSnapshot = vi.fn(async (_input: RequestInfo | URL) => ({
			ok: true,
			json: async () => ({ ...EMPTY_TRACE_RESPONSE, lookback_hours: 24 }),
		}));
		vi.stubGlobal("fetch", fetchSnapshot);

		render(
			createElement(TraceDataProvider, null, createElement(SourceStateProbe)),
		);

		await waitFor(() => expect(fetchSnapshot).toHaveBeenCalled());
		expect(fetchSnapshot).toHaveBeenCalledWith(
			expect.stringContaining("lookback_hours=24"),
		);
	});

	it("starts empty while the first live snapshot is pending", async () => {
		let resolveSnapshot: ((response: Response) => void) | null = null;
		vi.stubGlobal(
			"fetch",
			vi.fn(
				() =>
					new Promise<Response>((resolve) => {
						resolveSnapshot = resolve;
					}),
			),
		);

		render(
			createElement(TraceDataProvider, null, createElement(SourceStateProbe)),
		);

		expect(screen.getByTestId("source-state")).toHaveTextContent(
			"mock:true:0:0:0",
		);

		await waitFor(() => expect(resolveSnapshot).toBeTypeOf("function"));
		if (!resolveSnapshot) throw new Error("snapshot request was not started");

		await act(async () => {
			resolveSnapshot(
				new Response(
					JSON.stringify({
						ok: true,
						lookback_hours: 168,
						loaded_at: "2026-05-13T08:56:00.000Z",
						truncated: {},
						data: {
							events: [],
							rules: [streamRule("snapshot finding", { path: "src/live.py" })],
							results: [],
							subprocesses: [],
						},
					}),
					{ status: 200 },
				),
			);
		});

		await waitFor(() =>
			expect(screen.getByTestId("source-state")).toHaveTextContent(
				"streaming:false:1:0:0",
			),
		);
	});

	it("stores server-side snapshot summaries in source metadata", async () => {
		vi.stubGlobal(
			"fetch",
			vi.fn(async () => ({
				ok: true,
				json: async () => ({
					...EMPTY_TRACE_RESPONSE,
					summaries: {
						session_count: 3,
						decision_counts: { block: 1, allow: 2 },
						hottest_repos: [{ label: "slopgate", count: 4 }],
						top_rules: [{ rule_id: "PY-CODE-018", count: 1 }],
						subprocess_failures: 2,
					},
				}),
			})),
		);

		render(
			createElement(
				TraceDataProvider,
				null,
				createElement(SnapshotSummaryProbe),
			),
		);

		await waitFor(() =>
			expect(screen.getByTestId("snapshot-summary")).toHaveTextContent(
				'"session_count":3',
			),
		);
		expect(screen.getByTestId("snapshot-summary")).toHaveTextContent(
			'"subprocess_failures":2',
		);
	});

	it("replaces baked synthetic data with the first real snapshot", async () => {
		Object.defineProperty(window, "__SLOPGATE_DATA__", {
			configurable: true,
			writable: true,
			value: {
				events: [],
				rules: [streamRule("synthetic finding", { path: "src/synthetic.py" })],
				results: [],
				subprocesses: [],
			},
		});
		vi.stubGlobal(
			"fetch",
			vi.fn(async () => ({
				ok: true,
				json: async () => EMPTY_TRACE_RESPONSE,
			})),
		);

		render(
			createElement(TraceDataProvider, null, createElement(SourceStateProbe)),
		);

		expect(screen.getByTestId("source-state")).toHaveTextContent(
			"baked:true:1:0:0",
		);
		await waitFor(() =>
			expect(screen.getByTestId("source-state")).toHaveTextContent(
				"streaming:false:0:0:0",
			),
		);
	});

	it("ignores a stale snapshot after resetting to mock data", async () => {
		let resolveSnapshot: ((response: Response) => void) | null = null;
		vi.stubGlobal(
			"fetch",
			vi.fn(
				() =>
					new Promise<Response>((resolve) => {
						resolveSnapshot = resolve;
					}),
			),
		);

		render(
			createElement(TraceDataProvider, null, createElement(SourceActionProbe)),
		);

		await waitFor(() => expect(resolveSnapshot).toBeTypeOf("function"));
		fireEvent.click(screen.getByTestId("reset"));
		await waitFor(() =>
			expect(screen.getByTestId("source-state")).toHaveTextContent(
				/^mock:false:/,
			),
		);
		if (!resolveSnapshot) throw new Error("snapshot request was not started");

		await act(async () => {
			resolveSnapshot(
				new Response(
					JSON.stringify({
						ok: true,
						lookback_hours: 168,
						loaded_at: "2026-05-13T08:56:00.000Z",
						truncated: {},
						data: {
							events: [],
							rules: [streamRule("stale snapshot", { path: "src/stale.py" })],
							results: [],
							subprocesses: [],
						},
					}),
					{ status: 200 },
				),
			);
		});

		expect(screen.getByTestId("source-state")).toHaveTextContent(
			/^mock:false:/,
		);
	});

	it("ignores a stale snapshot after uploaded data is accepted", async () => {
		let resolveSnapshot: ((response: Response) => void) | null = null;
		vi.stubGlobal(
			"fetch",
			vi.fn(
				() =>
					new Promise<Response>((resolve) => {
						resolveSnapshot = resolve;
					}),
			),
		);

		render(
			createElement(TraceDataProvider, null, createElement(SourceActionProbe)),
		);

		await waitFor(() => expect(resolveSnapshot).toBeTypeOf("function"));
		fireEvent.click(screen.getByTestId("upload"));
		await waitFor(() =>
			expect(screen.getByTestId("source-state")).toHaveTextContent(
				"uploaded:false:1:0:0",
			),
		);
		if (!resolveSnapshot) throw new Error("snapshot request was not started");

		await act(async () => {
			resolveSnapshot(
				new Response(
					JSON.stringify({
						ok: true,
						lookback_hours: 168,
						loaded_at: "2026-05-13T08:56:00.000Z",
						truncated: {},
						data: { events: [], rules: [], results: [], subprocesses: [] },
					}),
					{ status: 200 },
				),
			);
		});

		expect(screen.getByTestId("source-state")).toHaveTextContent(
			"uploaded:false:1:0:0",
		);
	});
});
