import { join } from "node:path";
import { fileURLToPath } from "node:url";

export const WORKSPACE_ROOT = fileURLToPath(new URL("../", import.meta.url));
export const SNAPSHOT_PATH = join(WORKSPACE_ROOT, "contract-snapshot.json");

export const PLANNED_LISTENERS = [
  "agent_end",
  "before_agent_start",
  "input",
  "session_start",
  "session_stop",
  "tool_call",
  "tool_result",
  "turn_end",
  "user_bash",
  "user_python",
] as const;

export type PlannedListener = (typeof PLANNED_LISTENERS)[number];
export type PrimitiveType = "array" | "boolean" | "number" | "object" | "string";

export type FieldSchema = {
  readonly required: boolean;
  readonly type: string;
};

export type ResultSchema = {
  readonly fields: Readonly<Record<string, FieldSchema>>;
};

export type ListenerContract = ResultSchema & {
  readonly result_union: readonly string[];
};

export type BashInputContract = {
  readonly field_types: Readonly<Record<string, PrimitiveType>>;
  readonly optional_keys: readonly string[];
  readonly required_keys: readonly string[];
  readonly source: "BashToolInput";
  readonly variants: readonly Readonly<Record<string, PrimitiveType>>[];
};

export type IdentityEvidence = {
  readonly assertions: readonly ["same-within-session", "distinct-across-sessions"];
  readonly kind: "runner-test";
  readonly path: "scripts/session-identity.test.ts";
  readonly sha256: string;
};

export type ExportedSymbol = "ExtensionRunner" | "ExtensionRuntime" | "loadExtensionFromFactory";
export type ResultName =
  | "BeforeAgentStartEventResult"
  | "InputEventResult"
  | "SessionStopEventResult"
  | "ToolCallEventResult";

export type ContractSnapshot = {
  readonly bash_input: BashInputContract;
  readonly events: {
    readonly names: readonly string[];
    readonly user_bash: boolean;
    readonly user_python: boolean;
  };
  readonly exports: Readonly<
    Record<ExportedSymbol, { readonly subpath: string; readonly types: string }>
  >;
  readonly listeners: Readonly<Record<PlannedListener, ListenerContract>>;
  readonly packages: Readonly<Record<"@oh-my-pi/pi-coding-agent" | "@oh-my-pi/pi-tui", string>>;
  readonly results: Readonly<Record<ResultName, ResultSchema>>;
  readonly schema_version: 1;
  readonly session_identity_evidence: IdentityEvidence | null;
  readonly session_identity_source: "ctx.sessionManager.getSessionId()" | null;
  readonly session_stop: {
    readonly agent_message_content_union: readonly string[];
    readonly event: ResultSchema;
  };
  readonly session_stop_response_source: "last_assistant_message";
};

export class ContractLockError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ContractLockError";
  }
}

export function serializeSnapshot(snapshot: ContractSnapshot): string {
  return `${JSON.stringify(snapshot, null, 2)}\n`;
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
