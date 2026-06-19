import { AlertTriangle, CheckCircle2, FileText, LoaderCircle, RotateCcw, Upload, WifiOff, X } from "lucide-react";
import { type ChangeEvent, useCallback, useEffect, useRef, useState } from "react";
import type { SourceMode } from "@/context/TraceDataContext";
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
  const [status, setStatus] = useState<{
    accepted: number;
    rejected: string[];
  } | null>(null);
  const [statusVisible, setStatusVisible] = useState(false);
  const [loading, setLoading] = useState(false);

  const inputRef = useRef<HTMLInputElement>(null);
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);

  const lastEventLabel = formatLastEvent(lastStreamEventAt);
  const latestTraceLabel = formatTraceTimestamp(sourceMeta.latestDataAt);
  const lastAcceptedTraceLabel = formatTraceTimestamp(sourceMeta.lastAcceptedStreamRecordAt);

  const handleFiles = useCallback(
    async (files: FileList | File[]) => {
      setLoading(true);
      setStatus(null);
      setStatusVisible(false);
      if (timeoutRef.current) clearTimeout(timeoutRef.current);

      const result = await ingestFiles(Array.from(files));
      setStatus(result);
      setStatusVisible(true);
      setLoading(false);

      // Clear status display after 5 seconds
      timeoutRef.current = setTimeout(() => {
        setStatusVisible(false);
      }, 5000);
    },
    [ingestFiles],
  );

  // Setup global drag and drop listeners
  useEffect(() => {
    let dragCounter = 0;

    const handleDragEnter = (e: globalThis.DragEvent) => {
      e.preventDefault();
      dragCounter++;
      if (e.dataTransfer && e.dataTransfer.items.length > 0) {
        setIsDragging(true);
      }
    };

    const handleDragOver = (e: globalThis.DragEvent) => {
      e.preventDefault();
    };

    const handleDragLeave = (e: globalThis.DragEvent) => {
      e.preventDefault();
      dragCounter--;
      if (dragCounter === 0) {
        setIsDragging(false);
      }
    };

    const handleDrop = (e: globalThis.DragEvent) => {
      e.preventDefault();
      dragCounter = 0;
      setIsDragging(false);
      if (e.dataTransfer && e.dataTransfer.files.length > 0) {
        handleFiles(e.dataTransfer.files);
      }
    };

    window.addEventListener("dragenter", handleDragEnter);
    window.addEventListener("dragover", handleDragOver);
    window.addEventListener("dragleave", handleDragLeave);
    window.addEventListener("drop", handleDrop);

    return () => {
      window.removeEventListener("dragenter", handleDragEnter);
      window.removeEventListener("dragover", handleDragOver);
      window.removeEventListener("dragleave", handleDragLeave);
      window.removeEventListener("drop", handleDrop);
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, [handleFiles]);

  // Dot style based on state
  let dotElement: React.ReactNode = null;
  let statusText = "";
  let statusColorClass = "text-muted-foreground";

  if (loading) {
    dotElement = <LoaderCircle className="w-3 h-3 animate-spin text-primary" />;
    statusText = "Parsing traces…";
  } else if (sourceMeta.isSnapshotLoading) {
    dotElement = <LoaderCircle className="w-3 h-3 animate-spin text-primary" />;
    statusText = "Loading snapshot…";
  } else if (isLive) {
    if (streamState === "connecting") {
      dotElement = <LoaderCircle className="w-3 h-3 animate-spin text-amber-400" />;
      statusText = "Connecting...";
      statusColorClass = "text-amber-400 font-medium animate-pulse";
    } else if (streamState === "retrying") {
      dotElement = <WifiOff className="w-3 h-3 text-amber-400 animate-pulse" />;
      statusText = "Retrying...";
      statusColorClass = "text-amber-400 font-medium";
    } else {
      dotElement = (
        <span className="relative flex h-1.5 w-1.5">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
          <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500"></span>
        </span>
      );
      statusText = "Live connected";
      statusColorClass = "text-emerald-400 font-medium";
    }
  } else if (sourceMode === "uploaded") {
    dotElement = (
      <span className="relative flex h-1.5 w-1.5">
        <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-primary animate-pulse"></span>
      </span>
    );
    statusText = "Uploaded data";
    statusColorClass = "text-primary font-medium";
  } else {
    dotElement = <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/45" />;
    statusText = "Mock Mode";
    statusColorClass = "text-muted-foreground";
  }

  return (
    <>
      {isDragging && (
        <div className="fixed inset-0 bg-background/80 backdrop-blur-sm z-[9999] flex flex-col items-center justify-center border-2 border-dashed border-primary m-4 rounded-xl animate-in fade-in zoom-in-95 duration-150">
          <Upload className="w-12 h-12 text-primary animate-bounce mb-4" />
          <h3 className="text-lg font-semibold text-foreground">Drop trace files here</h3>
          <p className="text-sm text-muted-foreground mt-1">Accepts .jsonl, .json, .ndjson files</p>
        </div>
      )}

      <div className="flex items-center gap-3">
        {/* Temporary status badge shown for 5s after ingest */}
        {statusVisible && status && (
          <div className="flex items-center gap-2 animate-in fade-in slide-in-from-right-2 duration-200">
            {status.accepted > 0 && (
              <span className="text-[11px] text-emerald-400 font-medium flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3" />
                {status.accepted} file{status.accepted > 1 ? "s" : ""} ingested
              </span>
            )}
            {status.rejected.length > 0 && (
              <span className="text-[11px] text-signal-block font-medium flex items-center gap-1">
                <AlertTriangle className="w-3 h-3" />
                {status.rejected.length} file{status.rejected.length > 1 ? "s" : ""} rejected
              </span>
            )}
          </div>
        )}

        <div className="relative group">
          <button
            type="button"
            onClick={() => inputRef.current?.click()}
            className={cn(
              "flex items-center gap-2 rounded-full border px-3 py-1 text-[11px] transition-all bg-card/40 border-border hover:border-muted-foreground hover:bg-card/60 cursor-pointer shadow-sm",
              streamState === "connecting" || streamState === "retrying"
                ? "border-amber-500/30 bg-amber-500/5 hover:bg-amber-500/10"
                : isStreaming
                  ? "border-emerald-500/30 bg-emerald-500/5 hover:bg-emerald-500/10"
                  : sourceMode === "uploaded"
                    ? "border-primary/30 bg-primary/5 hover:bg-primary/10"
                    : "",
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
            {dotElement}
            <span className={statusColorClass}>{statusText}</span>
          </button>

          {/* Hover Dropdown card */}
          <div className="absolute right-0 top-full mt-2 w-80 rounded-md border border-border bg-popover p-4 shadow-xl hidden group-hover:block z-50 text-xs">
            <div className="font-medium text-foreground mb-2 flex items-center gap-1.5">
              {isLive && streamState === "retrying" ? (
                <WifiOff className="w-3.5 h-3.5 text-amber-400" />
              ) : isLive && streamState === "connecting" ? (
                <LoaderCircle className="w-3.5 h-3.5 animate-spin text-amber-400" />
              ) : isStreaming ? (
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
              ) : sourceMode === "uploaded" ? (
                <FileText className="w-3.5 h-3.5 text-primary" />
              ) : (
                <Upload className="w-3.5 h-3.5 text-muted-foreground" />
              )}
              <span>{SOURCE_MESSAGES[sourceMode]}</span>
            </div>

            {/* Metadata List */}
            <div className="space-y-1.5 text-muted-foreground mb-4 font-mono text-[10px]">
              {lastEventLabel && (
                <div className="flex justify-between">
                  <span>Last event:</span>
                  <span className="text-foreground">{lastEventLabel}</span>
                </div>
              )}
              {latestTraceLabel && (
                <div className="flex justify-between">
                  <span>Latest trace:</span>
                  <span className="text-foreground">{latestTraceLabel}</span>
                </div>
              )}
              {sourceMeta.acceptedStreamRecords > 0 && lastAcceptedTraceLabel && (
                <div className="flex justify-between">
                  <span>Last accepted:</span>
                  <span className="text-foreground">{lastAcceptedTraceLabel}</span>
                </div>
              )}
              {(sourceMeta.acceptedStreamRecords > 0 || sourceMeta.rejectedStreamRecords > 0) && (
                <div className="flex justify-between border-t border-border/50 pt-1.5 mt-1.5">
                  <span>Stream count:</span>
                  <span>
                    <span className="text-emerald-400">{sourceMeta.acceptedStreamRecords} ok</span>
                    {sourceMeta.rejectedStreamRecords > 0 && (
                      <span className="text-signal-block ml-1.5">{sourceMeta.rejectedStreamRecords} err</span>
                    )}
                  </span>
                </div>
              )}
            </div>

            {/* Ingestion results list inside the dropdown */}
            {status && (status.accepted > 0 || status.rejected.length > 0) && (
              <div className="border-t border-border/50 pt-2 mb-3 space-y-1">
                <div className="text-[10px] text-muted-foreground font-medium uppercase tracking-wider">Ingestion Status</div>
                {status.accepted > 0 && (
                  <div className="text-[10px] text-primary flex items-center gap-1">
                    <CheckCircle2 className="w-3 h-3 text-emerald-500" />
                    {status.accepted} file{status.accepted > 1 ? "s" : ""} ingested
                  </div>
                )}
                {status.rejected.map((msg: string) => (
                  <div key={msg} className="flex items-start gap-1 text-[10px] text-signal-block leading-tight">
                    <X className="w-3 h-3 shrink-0 mt-0.5" />
                    <span>{msg}</span>
                  </div>
                ))}
              </div>
            )}

            {/* Actions */}
            <div className="flex flex-col gap-1.5 pt-2 border-t border-border/50">
              <button
                type="button"
                onClick={() => inputRef.current?.click()}
                className="flex w-full items-center justify-center gap-2 rounded bg-primary py-1.5 text-[11px] font-semibold text-primary-foreground hover:bg-primary/90 transition-colors cursor-pointer"
              >
                <Upload className="w-3.5 h-3.5" />
                Upload Trace Files
              </button>

              {(isLive || sourceMode === "uploaded") && (
                <button
                  type="button"
                  onClick={() => {
                    resetToMock();
                    setStatus(null);
                  }}
                  className="flex w-full items-center justify-center gap-2 rounded border border-border bg-card py-1.5 text-[11px] font-medium text-muted-foreground hover:bg-muted hover:text-foreground transition-colors cursor-pointer"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                  Reset to Mock
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </>
  );
}
