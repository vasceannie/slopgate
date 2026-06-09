import { createContext } from "react";
import type { HookEvent, RuleFinding, HookResult, SubprocessRun } from "@/types/slopgate";

export interface TraceData {
  events: HookEvent[];
  rules: RuleFinding[];
  results: HookResult[];
  subprocesses: SubprocessRun[];
}

export type SourceMode = "mock" | "baked" | "uploaded" | "streaming";
export type StreamState = "idle" | "connecting" | "live" | "retrying";

export interface TraceSourceMeta {
  initialDataLatestAt: string | null;
  latestDataAt: string | null;
  snapshotLoadedAt: string | null;
  snapshotLookbackHours: number | null;
  snapshotError: string | null;
  snapshotTruncated: Record<string, number>;
  isSnapshotLoading: boolean;
  streamConnectedAt: number | null;
  lastAcceptedStreamRecordAt: string | null;
  acceptedStreamRecords: number;
  rejectedStreamRecords: number;
  totalRecords: number;
}

export interface TraceDataContextValue {
  data: TraceData;
  sourceMode: SourceMode;
  streamState: StreamState;
  sourceMeta: TraceSourceMeta;
  isStreaming: boolean;
  isLive: boolean;
  lastStreamEventAt: number | null;
  ingestFiles: (files: File[]) => Promise<{ accepted: number; rejected: string[] }>;
  refreshSnapshot: (lookbackHours: number) => Promise<void>;
  resetToMock: () => void;
}

export const TraceDataContext = createContext<TraceDataContextValue | null>(null);
