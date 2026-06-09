import { useState, useCallback, useRef, type ChangeEvent, type DragEvent } from "react";
import { Upload, FileText, X, RotateCcw, CheckCircle2, LoaderCircle, WifiOff, AlertTriangle } from "lucide-react";
import { type SourceMode } from "@/context/TraceDataContext";
import { useTraceDataSource } from "@/context/useTraceDataSource";
import { cn } from "@/lib/utils";

const SOURCE_MESSAGES: Record<SourceMode, string> = {
  streaming: "Live transport connected — accepting trace records",
  baked: "Snapshot loaded — connecting live stream",
  uploaded: "Uploaded data loaded — drop more files to merge",
  mock: "Drop .jsonl trace files or browse",
};

function formatLastEvent(ts: number | null): string | null {
  if (!ts) return null;
  const deltaSeconds = Math.max(0, Math.floor((Date.now() - ts) / 1000));
  if (deltaSeconds < 5) return "just now";
  if (deltaSeconds < 60) return `${deltaSeconds}s ago`;
  const deltaMinutes = Math.floor(deltaSeconds / 60);
  if (deltaMinutes < 60) return `${deltaMinutes}m ago`;
  const deltaHours = Math.floor(deltaMinutes / 60);
  return `${deltaHours}h ago`;
}

function formatTraceTimestamp(ts: string | null): string | null {
  if (!ts) return null;
  const date = new Date(ts);
  if (Number.isNaN(date.getTime())) return ts;
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function FileDropZone() {
  const { isLive, isStreaming, sourceMode, streamState, sourceMeta, lastStreamEventAt, ingestFiles, resetToMock } = useTraceDataSource();
  const [isDragging, setIsDragging] = useState(false);
  const [status, setStatus] = useState<{ accepted: number; rejected: string[] } | null>(null);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const lastEventLabel = formatLastEvent(lastStreamEventAt);
  const latestTraceLabel = formatTraceTimestamp(sourceMeta.latestDataAt);
  const lastAcceptedTraceLabel = formatTraceTimestamp(sourceMeta.lastAcceptedStreamRecordAt);

  const handleFiles = useCallback(async (files: FileList | File[]) => {
    setLoading(true);
    setStatus(null);
    const result = await ingestFiles(Array.from(files));
    setStatus(result);
    setLoading(false);
  }, [ingestFiles]);

  const onDrop = useCallback((e: DragEvent<HTMLButtonElement>) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files.length > 0) handleFiles(e.dataTransfer.files);
  }, [handleFiles]);

  const onDragOver = useCallback((e: DragEvent<HTMLButtonElement>) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const onDragLeave = useCallback(() => setIsDragging(false), []);

  return (
    <div className="relative">
      <button
        type="button"
        onDrop={onDrop}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onClick={() => inputRef.current?.click()}
        className={cn(
          "flex w-full items-center gap-3 rounded-md border border-dashed px-4 py-2.5 text-left cursor-pointer transition-all",
          isLive && "pr-28",
          isDragging
            ? "border-primary bg-primary/5 glow-green"
            : "border-border hover:border-muted-foreground bg-card/30",
          loading && "opacity-60 pointer-events-none"
        )}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".jsonl,.json,.ndjson"
          multiple
          className="hidden"
          onChange={(e: ChangeEvent<HTMLInputElement>) => e.target.files && handleFiles(e.target.files)}
        />
        
        {loading ? (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <div className="w-3 h-3 border border-primary border-t-transparent rounded-full animate-spin" />
            Parsing traces…
          </div>
        ) : sourceMeta.isSnapshotLoading ? (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <LoaderCircle className="w-3.5 h-3.5 animate-spin text-primary" />
            Loading live trace snapshot before rendering charts…
          </div>
        ) : isLive ? (
          <div className="flex flex-wrap items-center gap-2 text-xs">
            {streamState === "connecting" ? (
              <>
                <LoaderCircle className="w-3.5 h-3.5 animate-spin text-amber-400" />
                <span className="font-medium text-amber-300">{SOURCE_MESSAGES[sourceMode]}</span>
                <span className="rounded-full border border-amber-500/40 bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-amber-300">CONNECTING</span>
              </>
            ) : streamState === "retrying" ? (
              <>
                <WifiOff className="w-3.5 h-3.5 text-amber-400" />
                <span className="font-medium text-amber-300">Live stream interrupted — retrying with snapshot data</span>
                <span className="rounded-full border border-amber-500/40 bg-amber-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-amber-300">RETRYING</span>
              </>
            ) : (
              <>
                <CheckCircle2 className="w-3.5 h-3.5 text-primary" />
                <span className="text-primary font-medium">{SOURCE_MESSAGES[sourceMode]}</span>
                {isStreaming && <span className="text-emerald-400 font-semibold">● LIVE</span>}
              </>
            )}
            {lastEventLabel && (
              <span className="text-muted-foreground">transport event {lastEventLabel}</span>
            )}
            {latestTraceLabel && (
              <span className="text-muted-foreground">dataset latest {latestTraceLabel}</span>
            )}
            {lastAcceptedTraceLabel && sourceMeta.acceptedStreamRecords > 0 && (
              <span className="text-muted-foreground">accepted trace {lastAcceptedTraceLabel}</span>
            )}
            {sourceMeta.rejectedStreamRecords > 0 && (
              <span className="flex items-center gap-1 text-amber-300">
                <AlertTriangle className="w-3 h-3" /> {sourceMeta.rejectedStreamRecords} stream record{sourceMeta.rejectedStreamRecords === 1 ? "" : "s"} rejected
              </span>
            )}
          </div>
        ) : (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Upload className="w-3.5 h-3.5" />
            {SOURCE_MESSAGES.mock} or <span className="text-primary underline">browse</span>
            <span className="text-muted-foreground/60 ml-1">(events, rules, results, subprocess)</span>
          </div>
        )}
      </button>

      {isLive && !loading && (
        <button
          type="button"
          onClick={() => { resetToMock(); setStatus(null); }}
          className="absolute right-3 top-1/2 flex -translate-y-1/2 items-center gap-1 text-[10px] text-muted-foreground transition-colors hover:text-foreground"
        >
          <RotateCcw className="w-3 h-3" /> Reset to mock
        </button>
      )}

      {status && status.rejected.length > 0 && (
        <div className="mt-1.5 space-y-0.5">
          {status.rejected.map((msg: string) => (
            <div key={msg} className="flex items-center gap-1.5 text-[10px] text-signal-block">
              <X className="w-3 h-3 shrink-0" /> {msg}
            </div>
          ))}
        </div>
      )}

      {status && status.accepted > 0 && (
        <div className="mt-1 text-[10px] text-primary flex items-center gap-1.5">
          <FileText className="w-3 h-3" />
          {status.accepted} file{status.accepted > 1 ? "s" : ""} ingested
        </div>
      )}
    </div>
  );
}
