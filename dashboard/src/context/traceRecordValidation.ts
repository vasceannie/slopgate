import type { HookEvent, HookResult, RuleFinding, SubprocessRun } from "@/types/slopgate";

export type TraceRecordType = "event" | "rule" | "result" | "subprocess" | "ignored";

export type AcceptedTraceRecord =
  | { type: "event"; record: HookEvent }
  | { type: "rule"; record: RuleFinding }
  | { type: "result"; record: HookResult }
  | { type: "subprocess"; record: SubprocessRun }
  | { type: "ignored" };

function hasTraceIdentity(obj: Record<string, unknown>): boolean {
  return (
    typeof obj.timestamp === "string"
    && typeof obj.platform === "string"
    && typeof obj.event_name === "string"
    && typeof obj.session_id === "string"
    && typeof obj.tool_name === "string"
  );
}

export function classifyLine(obj: Record<string, unknown>): TraceRecordType | null {
  // subprocess: has command + returncode
  if ("command" in obj && "returncode" in obj) return "subprocess";
  // result rows intentionally do not carry event-only candidate path/language metadata.
  if ("findings" in obj && Array.isArray(obj.findings)) return "result";
  // rules.jsonl also contains timing/metric rows keyed by rule_id; those are not UI findings.
  if ("rule_id" in obj) {
    if (hasTraceIdentity(obj) && "decision" in obj && "severity" in obj) return "rule";
    return "ignored";
  }
  // event: has the full event identity shape, including candidate path/language metadata.
  if (hasTraceIdentity(obj)) return "event";
  return null;
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function isHookEventRecord(obj: unknown): obj is HookEvent {
  if (typeof obj !== "object" || obj === null) return false;
  const o = obj as Record<string, unknown>;
  return (
    hasTraceIdentity(o)
    && isStringArray(o.candidate_paths)
    && isStringArray(o.languages)
  );
}

function isRuleFindingRecord(obj: unknown): obj is RuleFinding {
  if (typeof obj !== "object" || obj === null) return false;
  const o = obj as Record<string, unknown>;
  return (
    hasTraceIdentity(o)
    && typeof o.rule_id === "string"
    && typeof o.severity === "string"
    && (typeof o.decision === "string" || o.decision === null)
    && (typeof o.message === "string" || o.message === null)
    && (typeof o.additional_context === "string" || o.additional_context === null)
    && typeof o.metadata === "object"
    && o.metadata !== null
  );
}

function isHookResultRecord(obj: unknown): obj is HookResult {
  if (typeof obj !== "object" || obj === null) return false;
  const o = obj as Record<string, unknown>;
  return (
    hasTraceIdentity(o)
    && Array.isArray(o.findings)
    && (Array.isArray(o.errors) || o.errors === null)
    && (typeof o.output === "object" || o.output === null || o.output === undefined)
  );
}

function isSubprocessRunRecord(obj: unknown): obj is SubprocessRun {
  if (typeof obj !== "object" || obj === null) return false;
  const o = obj as Record<string, unknown>;
  return (
    typeof o.timestamp === "string"
    && typeof o.event_name === "string"
    && typeof o.session_id === "string"
    && typeof o.command === "string"
    && typeof o.cwd === "string"
    && typeof o.returncode === "number"
    && typeof o.stdout === "string"
    && typeof o.stderr === "string"
    && typeof o.duration_ms === "number"
  );
}

export function coerceTraceRecord(obj: Record<string, unknown>): AcceptedTraceRecord | null {
  const type = classifyLine(obj);
  if (type === "event" && isHookEventRecord(obj)) return { type, record: obj };
  if (type === "rule" && isRuleFindingRecord(obj)) return { type, record: obj };
  if (type === "result" && isHookResultRecord(obj)) return { type, record: obj };
  if (type === "subprocess" && isSubprocessRunRecord(obj)) return { type, record: obj };
  if (type === "ignored") return { type };
  return null;
}
