import {
	type ReactNode,
	useCallback,
	useEffect,
	useMemo,
	useRef,
	useState,
} from "react";
import { generateMockData } from "@/data/mockTraces";
import type {
	HookEvent,
	HookResult,
	RuleFinding,
	SubprocessRun,
} from "@/types/slopgate";
import {
	type SourceMode,
	type StreamState,
	type TraceData,
	TraceDataContext,
	type TraceSourceMeta,
} from "./traceDataContext";
import { coerceTraceRecord } from "./traceRecordValidation";

export type {
	SourceMode,
	StreamState,
	TraceSourceMeta,
} from "./traceDataContext";

type AppendOutcome = "accepted" | "ignored" | "rejected";

interface SnapshotResponse {
	ok?: boolean;
	lookback_hours?: number;
	loaded_at?: string;
	truncated?: Record<string, number>;
	data?: Partial<TraceData>;
	error?: string;
}

async function parseJSONLFile(file: File): Promise<{
	events: HookEvent[];
	rules: RuleFinding[];
	results: HookResult[];
	subprocesses: SubprocessRun[];
}> {
	const text = await file.text();
	const lines = text.split("\n").filter((l) => l.trim());
	const events: HookEvent[] = [];
	const rules: RuleFinding[] = [];
	const results: HookResult[] = [];
	const subprocesses: SubprocessRun[] = [];

	for (const line of lines) {
		try {
			const obj = JSON.parse(line) as Record<string, unknown>;
			const accepted = coerceTraceRecord(obj);
			if (accepted?.type === "event") events.push(accepted.record);
			else if (accepted?.type === "rule") rules.push(accepted.record);
			else if (accepted?.type === "result") results.push(accepted.record);
			else if (accepted?.type === "subprocess")
				subprocesses.push(accepted.record);
		} catch {
			// skip malformed lines
		}
	}
	return { events, rules, results, subprocesses };
}

const MAX_RECORDS_PER_CATEGORY = 250000;

const EMPTY_TRACE_DATA: TraceData = {
	events: [],
	rules: [],
	results: [],
	subprocesses: [],
};

function latestTimestamp(items: Array<{ timestamp?: string }>): string | null {
	let latest: string | null = null;
	for (const item of items) {
		if (typeof item.timestamp !== "string" || !item.timestamp) continue;
		if (latest === null || item.timestamp > latest) latest = item.timestamp;
	}
	return latest;
}

function latestTraceTimestamp(data: TraceData): string | null {
	return latestTimestamp([
		...data.events,
		...data.rules,
		...data.results,
		...data.subprocesses,
	]);
}

function recordTimestamp(obj: Record<string, unknown>): string | null {
	return typeof obj.timestamp === "string" && obj.timestamp
		? obj.timestamp
		: null;
}

function stableRecordValue(value: unknown): unknown {
	if (Array.isArray(value)) return value.map(stableRecordValue);
	if (value && typeof value === "object") {
		return Object.fromEntries(
			Object.entries(value as Record<string, unknown>)
				.sort(([left], [right]) => left.localeCompare(right))
				.map(([key, child]) => [key, stableRecordValue(child)]),
		);
	}
	return value;
}

function recordKey(item: object): string {
	return JSON.stringify(stableRecordValue(item));
}

function appendBoundedUnique<T extends object>(items: T[], item: T): T[] {
	const key = recordKey(item);
	if (items.some((existing) => recordKey(existing) === key)) return items;
	if (items.length >= MAX_RECORDS_PER_CATEGORY)
		return [...items.slice(1), item];
	return [...items, item];
}

function coerceSnapshotData(snapshot: SnapshotResponse): TraceData {
	const data = snapshot.data ?? {};
	return {
		events: data.events ?? [],
		rules: data.rules ?? [],
		results: data.results ?? [],
		subprocesses: data.subprocesses ?? [],
	};
}

/** Check for pre-baked data injected by build-standalone into window.__SLOPGATE_DATA__ */
function getInitialData(): { data: TraceData; sourceMode: SourceMode } {
	const w = window as unknown as { __SLOPGATE_DATA__?: TraceData };
	if (w.__SLOPGATE_DATA__) {
		const d = w.__SLOPGATE_DATA__;
		return {
			data: {
				events: d.events ?? [],
				rules: d.rules ?? [],
				results: d.results ?? [],
				subprocesses: d.subprocesses ?? [],
			},
			sourceMode: "baked",
		};
	}
	return { data: EMPTY_TRACE_DATA, sourceMode: "mock" };
}

export function TraceDataProvider({ children }: { children: ReactNode }) {
	const initial = getInitialData();
	const initialDataLatestAt = latestTraceTimestamp(initial.data);
	const [data, setData] = useState<TraceData>(initial.data);
	const [sourceMode, setSourceMode] = useState<SourceMode>(initial.sourceMode);
	const [streamState, setStreamState] = useState<StreamState>(
		initial.sourceMode === "baked" ? "connecting" : "idle",
	);
	const [isStreaming, setStreaming] = useState(false);
	const [lastStreamEventAt, setLastStreamEventAt] = useState<number | null>(
		null,
	);
	const [streamConnectedAt, setStreamConnectedAt] = useState<number | null>(
		null,
	);
	const [lastAcceptedStreamRecordAt, setLastAcceptedStreamRecordAt] = useState<
		string | null
	>(null);
	const [snapshotLoadedAt, setSnapshotLoadedAt] = useState<string | null>(null);
	const [snapshotLookbackHours, setSnapshotLookbackHours] = useState<
		number | null
	>(null);
	const [snapshotError, setSnapshotError] = useState<string | null>(null);
	const [snapshotTruncated, setSnapshotTruncated] = useState<
		Record<string, number>
	>({});
	const [isSnapshotLoading, setSnapshotLoading] = useState(
		initial.sourceMode === "mock",
	);
	const [acceptedStreamRecords, setAcceptedStreamRecords] = useState(0);
	const [rejectedStreamRecords, setRejectedStreamRecords] = useState(0);
	const [shouldConnectStream, setShouldConnectStream] = useState(
		initial.sourceMode === "baked",
	);
	const eventSourceRef = useRef<EventSource | null>(null);
	const snapshotRequestVersionRef = useRef(0);

	const appendRecord = useCallback(
		(obj: Record<string, unknown>): AppendOutcome => {
			const accepted = coerceTraceRecord(obj);
			if (!accepted) return "rejected";
			if (accepted.type === "ignored") return "ignored";
			if (accepted.type === "event") {
				setData((prev: TraceData) => ({
					...prev,
					events: appendBoundedUnique(prev.events, accepted.record),
				}));
				return "accepted";
			}
			if (accepted.type === "rule") {
				setData((prev: TraceData) => ({
					...prev,
					rules: appendBoundedUnique(prev.rules, accepted.record),
				}));
				return "accepted";
			}
			if (accepted.type === "result") {
				setData((prev: TraceData) => ({
					...prev,
					results: appendBoundedUnique(prev.results, accepted.record),
				}));
				return "accepted";
			}
			if (accepted.type === "subprocess") {
				setData((prev: TraceData) => ({
					...prev,
					subprocesses: appendBoundedUnique(prev.subprocesses, accepted.record),
				}));
				return "accepted";
			}
			return "rejected";
		},
		[],
	);

	useEffect(() => {
		if (!shouldConnectStream) return;

		setStreamState("connecting");
		const basePath =
			document
				.querySelector("base")
				?.getAttribute("href")
				?.replace(/\/$/, "") ?? "";
		const eventSource = new EventSource(
			`${window.location.origin}${basePath}/api/stream`,
		);
		eventSourceRef.current = eventSource;

		eventSource.onopen = () => {
			setStreaming(true);
			setSourceMode("streaming");
			setStreamState("live");
			setStreamConnectedAt(Date.now());
		};

		eventSource.onmessage = (e) => {
			setStreaming(true);
			setStreamState("live");
			setLastStreamEventAt(Date.now());
			try {
				const obj = JSON.parse(e.data) as Record<string, unknown>;
				const outcome = appendRecord(obj);
				if (outcome === "accepted") {
					setAcceptedStreamRecords((count) => count + 1);
					const timestamp = recordTimestamp(obj);
					if (timestamp) setLastAcceptedStreamRecordAt(timestamp);
				} else if (outcome === "rejected") {
					setRejectedStreamRecords((count) => count + 1);
				}
			} catch {
				setRejectedStreamRecords((count) => count + 1);
			}
		};

		// Let EventSource handle reconnects on transient disconnects.
		eventSource.onerror = () => {
			setStreaming(false);
			setStreamState("retrying");
		};

		return () => {
			eventSource.close();
			if (eventSourceRef.current === eventSource) {
				eventSourceRef.current = null;
			}
			setStreaming(false);
			setStreamState("idle");
		};
	}, [appendRecord, shouldConnectStream]);

	const refreshSnapshot = useCallback(async (lookbackHours: number) => {
		const hours = Math.max(1, Math.min(Math.ceil(lookbackHours), 720));
		const basePath =
			document
				.querySelector("base")
				?.getAttribute("href")
				?.replace(/\/$/, "") ?? "";
		const requestVersion = snapshotRequestVersionRef.current + 1;
		snapshotRequestVersionRef.current = requestVersion;
		setSnapshotLoading(true);
		try {
			const response = await fetch(
				`${window.location.origin}${basePath}/api/snapshot?lookback_hours=${hours}`,
			);
			const snapshot = (await response.json()) as SnapshotResponse;
			if (snapshotRequestVersionRef.current !== requestVersion) return;
			if (!response.ok || snapshot.ok === false) {
				throw new Error(snapshot.error || `snapshot HTTP ${response.status}`);
			}
			const nextData = coerceSnapshotData(snapshot);
			setData(nextData);
			setSourceMode("streaming");
			setSnapshotLoadedAt(snapshot.loaded_at ?? new Date().toISOString());
			setSnapshotLookbackHours(snapshot.lookback_hours ?? hours);
			setSnapshotError(null);
			setSnapshotTruncated(snapshot.truncated ?? {});
			setShouldConnectStream(true);
		} catch (error) {
			if (snapshotRequestVersionRef.current === requestVersion) {
				setSnapshotError(
					error instanceof Error ? error.message : String(error),
				);
			}
		} finally {
			if (snapshotRequestVersionRef.current === requestVersion) {
				setSnapshotLoading(false);
			}
		}
	}, []);

	useEffect(() => {
		void refreshSnapshot(168);
	}, [refreshSnapshot]);

	const ingestFiles = useCallback(async (files: File[]) => {
		snapshotRequestVersionRef.current += 1;
		if (eventSourceRef.current) {
			eventSourceRef.current.close();
			eventSourceRef.current = null;
		}
		setShouldConnectStream(false);
		setStreaming(false);
		setStreamState("idle");
		setLastStreamEventAt(null);
		setStreamConnectedAt(null);
		setLastAcceptedStreamRecordAt(null);
		setSnapshotLoadedAt(null);
		setSnapshotLookbackHours(null);
		setSnapshotError(null);
		setSnapshotTruncated({});
		setSnapshotLoading(false);
		setAcceptedStreamRecords(0);
		setRejectedStreamRecords(0);

		let accepted = 0;
		const rejected: string[] = [];
		const merged: TraceData = {
			events: [],
			rules: [],
			results: [],
			subprocesses: [],
		};

		for (const file of files) {
			if (
				!file.name.endsWith(".jsonl") &&
				!file.name.endsWith(".json") &&
				!file.name.endsWith(".ndjson")
			) {
				rejected.push(`${file.name}: unsupported format`);
				continue;
			}
			try {
				const parsed = await parseJSONLFile(file);
				const total =
					parsed.events.length +
					parsed.rules.length +
					parsed.results.length +
					parsed.subprocesses.length;
				if (total === 0) {
					rejected.push(`${file.name}: no recognizable trace records`);
					continue;
				}
				merged.events.push(...parsed.events);
				merged.rules.push(...parsed.rules);
				merged.results.push(...parsed.results);
				merged.subprocesses.push(...parsed.subprocesses);
				accepted++;
			} catch {
				rejected.push(`${file.name}: parse error`);
			}
		}

		if (accepted > 0) {
			// Sort all by timestamp
			merged.events.sort((a, b) => a.timestamp.localeCompare(b.timestamp));
			merged.rules.sort((a, b) => a.timestamp.localeCompare(b.timestamp));
			merged.results.sort((a, b) => a.timestamp.localeCompare(b.timestamp));
			merged.subprocesses.sort((a, b) =>
				a.timestamp.localeCompare(b.timestamp),
			);
			setData(merged);
			setSourceMode("uploaded");
			setLastStreamEventAt(null);
		}
		return { accepted, rejected };
	}, []);

	const resetToMock = useCallback(() => {
		snapshotRequestVersionRef.current += 1;
		if (eventSourceRef.current) {
			eventSourceRef.current.close();
			eventSourceRef.current = null;
		}
		setShouldConnectStream(false);
		setStreaming(false);
		setStreamState("idle");
		setLastStreamEventAt(null);
		setStreamConnectedAt(null);
		setLastAcceptedStreamRecordAt(null);
		setSnapshotLoadedAt(null);
		setSnapshotLookbackHours(null);
		setSnapshotError(null);
		setSnapshotTruncated({});
		setSnapshotLoading(false);
		setAcceptedStreamRecords(0);
		setRejectedStreamRecords(0);
		setData(generateMockData());
		setSourceMode("mock");
	}, []);

	const isLive = sourceMode !== "mock";
	const latestDataAt = useMemo(() => latestTraceTimestamp(data), [data]);
	const totalRecords =
		data.events.length +
		data.rules.length +
		data.results.length +
		data.subprocesses.length;
	const sourceMeta = useMemo<TraceSourceMeta>(
		() => ({
			initialDataLatestAt,
			latestDataAt,
			snapshotLoadedAt,
			snapshotLookbackHours,
			snapshotError,
			snapshotTruncated,
			isSnapshotLoading,
			streamConnectedAt,
			lastAcceptedStreamRecordAt,
			acceptedStreamRecords,
			rejectedStreamRecords,
			totalRecords,
		}),
		[
			acceptedStreamRecords,
			initialDataLatestAt,
			isSnapshotLoading,
			lastAcceptedStreamRecordAt,
			latestDataAt,
			rejectedStreamRecords,
			snapshotError,
			snapshotLoadedAt,
			snapshotLookbackHours,
			snapshotTruncated,
			streamConnectedAt,
			totalRecords,
		],
	);

	return (
		<TraceDataContext.Provider
			value={{
				data,
				sourceMode,
				streamState,
				sourceMeta,
				isStreaming,
				isLive,
				lastStreamEventAt,
				ingestFiles,
				refreshSnapshot,
				resetToMock,
			}}
		>
			{children}
		</TraceDataContext.Provider>
	);
}
