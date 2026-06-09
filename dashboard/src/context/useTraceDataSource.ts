import { useContext } from "react";
import { TraceDataContext } from "./traceDataContext";

export function useTraceDataSource() {
  const ctx = useContext(TraceDataContext);
  if (!ctx) throw new Error("useTraceDataSource must be used within TraceDataProvider");
  return ctx;
}
