import { AlertOctagon, CheckCircle2, FilterX, Info, ShieldAlert } from "lucide-react";
import { memo, type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { resolveDecision } from "@/hooks/useTraceData";
import type { SessionData, TimelineEntry, TimelineFinding } from "@/lib/sessionHelpers";
import { correlationStatus, initialTimelineSelection, timelineRowSummary } from "@/lib/sessionHelpers";
import { cn } from "@/lib/utils";
import type { Decision, HookEvent, HookResult, LineageRole } from "@/types/slopgate";
import { FlagButton } from "./FlagButton";
import { TimelineVerdictStrip } from "./TimelineVerdictStrip";

const PAGE_SIZE = 50;
const TOOL_DRILLDOWN_CORRELATION_WINDOW_MS = 120_000;

type DetailToggle = "findings" | "errors";
type PayloadViewMode = "pretty" | "raw";

const DETAIL_TOGGLE_LABELS: Record<DetailToggle, string> = {
  findings: "Has findings",
  errors: "Has errors",
};

const DETAIL_TOGGLES: DetailToggle[] = ["findings", "errors"];

type EventMatch = {
  event: HookEvent;
  index: number;
};

type LineageSource = {
  session_id: string;
  parent_session_id?: string | null;
  root_session_id?: string | null;
  origin_session_id?: string | null;
  lineage_role?: LineageRole | null;
};

type SourceOrigin = {
  roleLabel: string;
  sessionLabel: string;
  fullSessionId: string;
};

type DrilldownFields = Pick<
  TimelineEntry,
  | "model"
  | "provider"
  | "command"
  | "tool_output"
  | "candidate_paths"
  | "tool_context"
  | "url_context"
  | "patch_text"
  | "edit_before"
  | "edit_after"
  | "tool_input_json"
>;

type ToolInputDetails = {
  command?: string | null;
  patch_text?: string | null;
  edit_before?: string | null;
  edit_after?: string | null;
  tool_output?: string | null;
  tool_input_json?: string | null;
  candidate_paths?: string[];
  url_context?: string[];
  tool_context?: string[];
};

type ResultFinding = HookResult["findings"][number];

type FormattedHookOutput = {
  label: string;
  value: string;
  variant: "context" | "decision" | "metadata" | "raw";
};

type FocusedEditPayload = {
  prettyText: string;
  rawText: string;
};

type EvidenceCode = {
  language: "JSON" | "Python" | "YAML" | "Text";
  text: string;
};

const FILE_CONTEXT_PATTERN =
  /(^\.?\.?\/|\/|\\|\.(py|ts|tsx|js|jsx|json|md|toml|ya?ml|sh|css|html|tool)$|^(src|tests?|dashboard|bundle|docs|logs|scripts)$)/i;
const TOOL_EXPRESSION_PATTERN = /[{}(),]|\\[.dws]|\b(button|document|window|String)\b/;
const URL_CONTEXT_PATTERN = /^(https?:)?\/\//i;
const LOW_VALUE_CONTEXT_PATTERN = /^[{,\s]+|\b(textContent|className|length)\b|['")]+\./;
const APPLY_PATCH_MARKER = "*** Begin Patch";
const UNIFIED_DIFF_GIT_HEADER_PATTERN = /^diff --git\s+a\/.+\s+b\/.+/m;
const UNIFIED_DIFF_FILE_HEADER_PATTERN = /^---\s+(?:a\/.+|\/dev\/null)\s*\r?\n\+\+\+\s+(?:b\/.+|\/dev\/null)/m;
const PYTHON_CONTEXT_PATTERN = /(^|\n)\s*(class|def|from|import|return|with|if|elif|else|try|except)\b|(^|\n)\s*@[\w.]+/;
const YAML_CONTEXT_PATTERN = /(^|\n)\s*[\w.-]+:\s*\S/;
const CODE_TOKEN_PATTERN =
  /("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\x60(?:\\.|[^\x60\\])*\x60|\b(?:true|false|null|undefined)\b|\b\d+(?:\.\d+)?\b|--?[\w-]+|https?:\/\/[^\s)]+|[#@][\w/-]+|{}[\](),.:;=])/g;

type DiffLineKind = "add" | "context" | "delete" | "file" | "hunk";

type CodeTokenKind = "boolean" | "comment" | "heading" | "key" | "link" | "number" | "operator" | "punctuation" | "string" | "text";

type CodeToken = {
  kind: CodeTokenKind;
  text: string;
};

function textField(record: Record<string, unknown> | null, fields: string[]): string | null {
  for (const field of fields) {
    const value = record?.[field];
    if (typeof value === "string" && value.trim()) return value;
  }
  return null;
}

function isFileContext(value: string): boolean {
  const trimmed = value.trim();
  return Boolean(
    trimmed && !URL_CONTEXT_PATTERN.test(trimmed) && !TOOL_EXPRESSION_PATTERN.test(trimmed) && FILE_CONTEXT_PATTERN.test(trimmed),
  );
}

function isUrlContext(value: string): boolean {
  return URL_CONTEXT_PATTERN.test(value.trim());
}

function isUsefulToolContext(value: string): boolean {
  const trimmed = value.trim();
  return Boolean(trimmed && !isFileContext(trimmed) && !isUrlContext(trimmed) && !LOW_VALUE_CONTEXT_PATTERN.test(trimmed));
}

function splitCandidateContext(candidatePaths: string[] | undefined): {
  candidate_paths?: string[];
  tool_context?: string[];
  url_context?: string[];
} {
  if (!candidatePaths?.length) return {};
  const filePaths = candidatePaths.filter(isFileContext);
  const urlContext = candidatePaths.filter(isUrlContext);
  const toolContext = candidatePaths.filter(isUsefulToolContext);
  return {
    candidate_paths: filePaths.length > 0 ? filePaths : undefined,
    tool_context: toolContext.length > 0 ? toolContext : undefined,
    url_context: urlContext.length > 0 ? urlContext : undefined,
  };
}

function outputRecord(value: unknown): Record<string, unknown> | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  return Object.fromEntries(Object.entries(value));
}

function hasDirectToolInputFields(record: Record<string, unknown>): boolean {
  return [
    "command",
    "cmd",
    "code",
    "patchText",
    "patch",
    "diff",
    "old_string",
    "oldString",
    "new_string",
    "newString",
    "file_path",
    "filePath",
    "path",
    "url",
    "uri",
  ].some((key) => record[key] !== undefined);
}

function textFromUnknown(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function commandFromOutput(output: Record<string, unknown> | null): string | null {
  const direct = textField(output, ["command", "cmd"]);
  if (direct) return direct;

  const nestedRecords = [
    outputRecord(output?.input),
    outputRecord(output?.tool_input),
    outputRecord(output?.toolInput),
    outputRecord(output?.tool_args),
    outputRecord(output?.args),
    outputRecord(output?.arguments),
  ];
  for (const record of nestedRecords) {
    const nested = textField(record, ["command", "cmd", "code"]);
    if (nested) return nested;
  }

  return null;
}

function toolInputFromOutput(output: Record<string, unknown> | null): Record<string, unknown> | null {
  if (!output) return null;
  const nested =
    outputRecord(output.input) ??
    outputRecord(output.tool_input) ??
    outputRecord(output.toolInput) ??
    outputRecord(output.tool_args) ??
    outputRecord(output.args) ??
    outputRecord(output.arguments);
  if (nested) return nested;
  return hasDirectToolInputFields(output) ? output : null;
}

function candidatePathsFromInput(input: Record<string, unknown> | null): string[] | undefined {
  if (!input) return undefined;
  const candidates = [input.file_path, input.filePath, input.path, input.url, input.uri].filter(
    (value): value is string => typeof value === "string" && Boolean(value.trim()),
  );
  return candidates.length > 0 ? candidates : undefined;
}

function nestedInputRecords(input: Record<string, unknown> | null): Record<string, unknown>[] {
  if (!input) return [];
  return [
    input,
    outputRecord(input.input),
    outputRecord(input.tool_input),
    outputRecord(input.toolInput),
    outputRecord(input.tool_args),
    outputRecord(input.args),
    outputRecord(input.arguments),
  ].filter((record): record is Record<string, unknown> => record !== null);
}

function nonEmptyObject(value: Record<string, unknown> | null): boolean {
  return value !== null && Object.keys(value).length > 0;
}

function jsonFromRecord(value: Record<string, unknown> | null): string | null {
  if (!nonEmptyObject(value)) return null;
  return JSON.stringify(value, null, 2);
}

function jsonRecordFromText(value: string): Record<string, unknown> | null {
  try {
    return outputRecord(JSON.parse(value));
  } catch {
    return null;
  }
}

function jsonValueFromText(value: string): unknown | null {
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

function formattedJsonValue(value: unknown): string {
  const formatted = JSON.stringify(value, null, 2);
  return formatted ?? String(value);
}

function textFromRecordKey(record: Record<string, unknown>, key: string): string | null {
  const value = record[key];
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "boolean" || typeof value === "number") return String(value);
  return null;
}

function splitHookMessage(value: string): string {
  return value
    .split(/\n(?=\[[A-Z0-9-]+\s*\|)/)
    .map((line) => line.trim())
    .filter(Boolean)
    .join("\n\n");
}

function appendHookOutputSection(
  sections: FormattedHookOutput[],
  record: Record<string, unknown>,
  keys: string[],
  label: string,
  variant: FormattedHookOutput["variant"],
) {
  const value = keys.map((key) => textFromRecordKey(record, key)).find((candidate): candidate is string => candidate !== null);
  if (!value) return;
  sections.push({ label, value: splitHookMessage(value), variant });
}

function formattedHookOutputSections(value: string): FormattedHookOutput[] {
  const root = jsonRecordFromText(value);
  if (!root) return [{ label: "Raw output", value, variant: "raw" }];
  const hookSpecific = outputRecord(root.hookSpecificOutput) ?? outputRecord(root.hook_specific_output);
  const records = hookSpecific ? [root, hookSpecific] : [root];
  const sections: FormattedHookOutput[] = [];

  for (const record of records) {
    appendHookOutputSection(sections, record, ["hookEventName", "hook_event_name"], "Hook event", "metadata");
    appendHookOutputSection(sections, record, ["action"], "Action", "metadata");
    appendHookOutputSection(sections, record, ["decision"], "Decision", "decision");
    appendHookOutputSection(sections, record, ["permissionDecision", "permission_decision"], "Permission decision", "decision");
    appendHookOutputSection(sections, record, ["continue"], "Continue", "decision");
    appendHookOutputSection(sections, record, ["reason"], "Reason", "decision");
    appendHookOutputSection(sections, record, ["permissionDecisionReason", "permission_decision_reason"], "Permission reason", "decision");
    appendHookOutputSection(sections, record, ["stopReason", "stop_reason"], "Stop reason", "decision");
    appendHookOutputSection(sections, record, ["context"], "Context", "context");
    appendHookOutputSection(sections, record, ["additionalContext", "additional_context"], "Additional context", "context");
    appendHookOutputSection(sections, record, ["systemMessage", "system_message"], "System message", "context");
    appendHookOutputSection(sections, record, ["updatedInput", "updated_input", "updated_args"], "Updated input", "metadata");
  }

  if (sections.length > 0) return sections;
  return [
    {
      label: "Raw output",
      value: JSON.stringify(root, null, 2),
      variant: "raw",
    },
  ];
}

function outputSectionClass(variant: FormattedHookOutput["variant"]): string {
  if (variant === "decision") return "border-signal-danger/20 bg-signal-danger/5";
  if (variant === "context") return "border-signal-ask/20 bg-signal-ask/5";
  if (variant === "metadata") return "border-primary/20 bg-primary/5";
  return "border-border/20 bg-background/50";
}

function isApplyPatchText(value: string): boolean {
  return value.includes(APPLY_PATCH_MARKER);
}

function isUnifiedDiffText(value: string): boolean {
  const trimmed = value.trimStart();
  return UNIFIED_DIFF_GIT_HEADER_PATTERN.test(trimmed) || UNIFIED_DIFF_FILE_HEADER_PATTERN.test(trimmed);
}

function isDiffText(value: string): boolean {
  return isApplyPatchText(value) || isUnifiedDiffText(value);
}

function normalizePatchPath(path: string): string {
  return path.trim() || "unknown";
}

function unifiedDiffHeaders(path: string, mode: "add" | "delete" | "update"): string[] {
  const normalizedPath = normalizePatchPath(path);
  if (mode === "add") {
    return [`diff --git a/${normalizedPath} b/${normalizedPath}`, "--- /dev/null", `+++ b/${normalizedPath}`];
  }
  if (mode === "delete") {
    return [`diff --git a/${normalizedPath} b/${normalizedPath}`, `--- a/${normalizedPath}`, "+++ /dev/null"];
  }
  return [`diff --git a/${normalizedPath} b/${normalizedPath}`, `--- a/${normalizedPath}`, `+++ b/${normalizedPath}`];
}

function applyPatchToUnifiedDiff(value: string): string {
  if (!isApplyPatchText(value)) return value;
  const output: string[] = [];
  for (const line of value.split("\n")) {
    if (line === "*** Begin Patch" || line === "*** End Patch") continue;
    if (line.startsWith("*** Update File: ")) {
      output.push(...unifiedDiffHeaders(line.slice(17), "update"));
      continue;
    }
    if (line.startsWith("*** Add File: ")) {
      output.push(...unifiedDiffHeaders(line.slice(14), "add"));
      continue;
    }
    if (line.startsWith("*** Delete File: ")) {
      output.push(...unifiedDiffHeaders(line.slice(17), "delete"));
      continue;
    }
    if (line.startsWith("*** Move to: ")) {
      output.push(`rename to ${normalizePatchPath(line.slice(13))}`);
      continue;
    }
    output.push(line);
  }
  return output.join("\n").trimEnd();
}

function diffLineKind(line: string): DiffLineKind {
  if (line.startsWith("@@")) return "hunk";
  if (line.startsWith("diff --git") || line.startsWith("--- ")) return "file";
  if (line.startsWith("+++ ")) return "file";
  if (line.startsWith("+")) return "add";
  if (line.startsWith("-")) return "delete";
  return "context";
}

function diffLineClass(kind: DiffLineKind): string {
  if (kind === "add") return "bg-signal-allow/10 text-signal-allow";
  if (kind === "delete") return "bg-signal-deny/10 text-signal-deny";
  if (kind === "hunk") return "bg-signal-ask/10 text-signal-ask";
  if (kind === "file") return "bg-primary/10 text-primary";
  return "text-foreground";
}

function keyedDiffLines(text: string): Array<{ id: string; line: string }> {
  const counts = new Map<string, number>();
  return text.split("\n").map((line) => {
    const count = counts.get(line) ?? 0;
    counts.set(line, count + 1);
    return { id: `${line.slice(0, 48)}:${count}`, line };
  });
}

function toolInputDetails(output: Record<string, unknown> | null): ToolInputDetails {
  return toolInputDetailsFromInput(toolInputFromOutput(output));
}

function toolInputDetailsFromInput(input: Record<string, unknown> | null): ToolInputDetails {
  const records = nestedInputRecords(input);
  const firstTextField = (fields: string[]) => {
    for (const record of records) {
      const value = textField(record, fields);
      if (value) return value;
    }
    return null;
  };
  const candidatePaths = records.flatMap((record) => candidatePathsFromInput(record) ?? []);
  const candidateContext = splitCandidateContext(candidatePaths.length > 0 ? candidatePaths : undefined);
  return {
    command: firstTextField(["command", "cmd", "code"]),
    patch_text: firstTextField(["patchText", "patch", "diff"]),
    edit_before: firstTextField(["old_string", "oldString", "before"]),
    edit_after: firstTextField(["new_string", "newString", "after"]),
    tool_output: firstTextField(["text", "content"]),
    tool_input_json: jsonFromRecord(input),
    ...candidateContext,
  };
}

function focusedEditPayload(entry: TimelineEntry): FocusedEditPayload | null {
  const before = textFromUnknown(entry.edit_before);
  const after = textFromUnknown(entry.edit_after);
  if (!before && !after) {
    return entry.patch_text
      ? {
          prettyText: isApplyPatchText(entry.patch_text) ? applyPatchToUnifiedDiff(entry.patch_text) : entry.patch_text,
          rawText: entry.patch_text,
        }
      : null;
  }
  return {
    prettyText: [
      "--- before",
      "+++ after",
      ...(before ?? "").split("\n").map((line) => `-${line}`),
      ...(after ?? "").split("\n").map((line) => `+${line}`),
    ].join("\n"),
    rawText: JSON.stringify({ before, after }, null, 2),
  };
}

function codeTokenKind(value: string): CodeTokenKind {
  if (value.startsWith("#") || value.startsWith("@")) return "comment";
  if (value.startsWith("http://") || value.startsWith("https://")) return "link";
  if (value.startsWith('"') || value.startsWith("'") || value.startsWith("`")) {
    return "string";
  }
  if (/^\d/.test(value)) return "number";
  if (["true", "false", "null", "undefined"].includes(value)) return "boolean";
  if (value.startsWith("-")) return "operator";
  if (/^{}[\](),.:;=]$/.test(value)) return "punctuation";
  return "text";
}

function tokenizeCodeLine(line: string): CodeToken[] {
  const trimmed = line.trimStart();
  if (trimmed.startsWith("#") || trimmed.startsWith("//")) {
    return [{ kind: "comment", text: line }];
  }
  if (trimmed.startsWith("---") || trimmed.startsWith("# ")) {
    return [{ kind: "heading", text: line }];
  }

  const tokens: CodeToken[] = [];
  let cursor = 0;
  for (const match of line.matchAll(CODE_TOKEN_PATTERN)) {
    const tokenText = match[0];
    const index = match.index ?? cursor;
    if (index > cursor) {
      tokens.push({ kind: "text", text: line.slice(cursor, index) });
    }
    tokens.push({ kind: codeTokenKind(tokenText), text: tokenText });
    cursor = index + tokenText.length;
  }
  if (cursor < line.length) tokens.push({ kind: "text", text: line.slice(cursor) });
  return tokens.length > 0 ? tokens : [{ kind: "text", text: line || " " }];
}

function highlightedValueClass(kind: CodeTokenKind): string {
  if (kind === "boolean") return "text-signal-ask";
  if (kind === "comment") return "text-muted-foreground";
  if (kind === "heading") return "font-semibold text-primary";
  if (kind === "key") return "text-primary";
  if (kind === "link") return "text-primary underline decoration-primary/30";
  if (kind === "number") return "text-signal-warn";
  if (kind === "operator") return "text-signal-ask";
  if (kind === "punctuation") return "text-muted-foreground";
  if (kind === "string") return "text-signal-allow";
  return "text-foreground";
}

function HighlightedValue({ token }: { token: CodeToken }) {
  return (
    <span data-token={token.kind} className={highlightedValueClass(token.kind)}>
      {token.text}
    </span>
  );
}

function keyedCodeTokens(tokens: CodeToken[]): Array<{ id: string; token: CodeToken }> {
  const counts = new Map<string, number>();
  return tokens.map((token) => {
    const signature = `${token.kind}:${token.text}`;
    const count = counts.get(signature) ?? 0;
    counts.set(signature, count + 1);
    return { id: `${signature}:${count}`, token };
  });
}

function yamlKeyMatch(line: string): { key: string; separator: string; value: string } | null {
  const match = /^(\s*[\w.-]+)(\s*:\s?)(.*)$/.exec(line);
  if (!match) return null;
  return { key: match[1], separator: match[2], value: match[3] };
}

function HighlightedCodeLine({ line }: { line: string }) {
  const yaml = yamlKeyMatch(line);
  if (yaml) {
    return (
      <span className="block min-w-max whitespace-pre" data-token="line">
        <span data-token="key" className={highlightedValueClass("key")}>
          {yaml.key}
        </span>
        <span data-token="punctuation" className={highlightedValueClass("punctuation")}>
          {yaml.separator}
        </span>
        {keyedCodeTokens(tokenizeCodeLine(yaml.value)).map(({ id, token }) => (
          <HighlightedValue key={id} token={token} />
        ))}
      </span>
    );
  }

  return (
    <span className="block min-w-max whitespace-pre" data-token="line">
      {keyedCodeTokens(tokenizeCodeLine(line)).map(({ id, token }) => (
        <HighlightedValue key={id} token={token} />
      ))}
    </span>
  );
}

function CodeBlock({ text }: { text: string }) {
  return (
    <pre className="max-h-56 max-w-full overflow-auto rounded border border-border/20 bg-background/50 p-2 text-foreground whitespace-pre-wrap">
      {keyedDiffLines(text).map(({ id, line }) => (
        <HighlightedCodeLine key={id} line={line} />
      ))}
    </pre>
  );
}

function evidenceCode(value: string): EvidenceCode {
  const trimmed = value.trim();
  const parsed = jsonValueFromText(trimmed);
  if (parsed !== null) {
    return { language: "JSON", text: formattedJsonValue(parsed) };
  }
  if (PYTHON_CONTEXT_PATTERN.test(trimmed)) {
    return { language: "Python", text: trimmed };
  }
  if (YAML_CONTEXT_PATTERN.test(trimmed)) {
    return { language: "YAML", text: trimmed };
  }
  return { language: "Text", text: trimmed };
}

function FindingEvidenceBlock({ text }: { text: string }) {
  const evidence = evidenceCode(text);
  return (
    <div className="mt-2 space-y-1">
      <div className="text-[9px] uppercase tracking-wider text-muted-foreground">Evidence ({evidence.language}):</div>
      <CodeBlock text={evidence.text} />
    </div>
  );
}

function PrettyJsonValue({ value, compactPatchText = false }: { value: unknown; compactPatchText?: boolean }) {
  if (typeof value === "string") {
    if (isDiffText(value)) {
      if (compactPatchText) {
        return (
          <span className="break-words text-foreground">
            {isApplyPatchText(value)
              ? "Captured apply_patch body. Use the dedicated diff panel for the pretty view or switch to Raw for the original JSON."
              : "Captured diff text. Use the dedicated diff panel for the pretty view or switch to Raw for the original JSON."}
          </span>
        );
      }
      return <DiffPreview text={isApplyPatchText(value) ? applyPatchToUnifiedDiff(value) : value} />;
    }
    if (value.includes("\n") || value.length > 120) {
      return <CodeBlock text={value} />;
    }
    return <span className="break-all text-foreground">{value}</span>;
  }
  if (typeof value === "number" || typeof value === "boolean" || value === null) {
    return <span className="rounded bg-muted/30 px-1.5 py-0.5 text-foreground">{String(value)}</span>;
  }
  return <CodeBlock text={formattedJsonValue(value)} />;
}

function PrettyJsonView({ text, compactPatchText = false }: { text: string; compactPatchText?: boolean }) {
  const parsed = jsonValueFromText(text);
  const record = outputRecord(parsed);
  if (!record) return <CodeBlock text={text} />;
  const entries = Object.entries(record);
  if (entries.length === 0) return <CodeBlock text="{}" />;
  return (
    <div className="space-y-1.5">
      {entries.map(([key, value]) => (
        <div key={key} className="rounded border border-border/20 bg-background/40 p-2">
          <div className="mb-1 text-[9px] uppercase tracking-wider text-muted-foreground">{key}</div>
          <PrettyJsonValue value={value} compactPatchText={compactPatchText} />
        </div>
      ))}
    </div>
  );
}

function PayloadPanel({ title, pretty, rawText }: { title: string; pretty: ReactNode; rawText: string }) {
  const [mode, setMode] = useState<PayloadViewMode>("pretty");
  return (
    <section>
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <span className="text-muted-foreground select-none">{title}: </span>
        <div className="flex items-center gap-1">
          {(["pretty", "raw"] as const).map((option) => (
            <button
              key={option}
              type="button"
              aria-label={`${title} ${option} view`}
              onClick={() => setMode(option)}
              className={cn(
                "rounded border px-1.5 py-0.5 text-[9px] uppercase tracking-wider transition-colors",
                mode === option
                  ? "border-primary/40 bg-primary/15 text-primary"
                  : "border-border/40 bg-muted/20 text-muted-foreground hover:text-foreground",
              )}
            >
              {option}
            </button>
          ))}
        </div>
      </div>
      {mode === "pretty" ? pretty : <CodeBlock text={rawText} />}
    </section>
  );
}

function FormattedOutputValue({ value }: { value: string }) {
  const parsed = jsonValueFromText(value);
  if (parsed !== null) return <PrettyJsonValue value={parsed} />;
  return <CodeBlock text={value} />;
}

function PrettyOutputView({ text }: { text: string }) {
  return (
    <div className="space-y-1.5">
      {formattedHookOutputSections(text).map((section) => (
        <div
          key={`${section.label}:${section.value.slice(0, 32)}`}
          className={cn("rounded border p-2", outputSectionClass(section.variant))}
        >
          <div className="mb-1 text-[9px] uppercase tracking-wider text-muted-foreground">{section.label}</div>
          <FormattedOutputValue value={section.value} />
        </div>
      ))}
    </div>
  );
}

function DiffPreview({ text }: { text: string }) {
  return (
    <pre className="mt-1 max-h-56 max-w-full overflow-auto rounded border border-border/20 bg-background/50 py-2 text-foreground">
      {keyedDiffLines(text).map(({ id, line }) => (
        <span key={id} className={cn("block min-w-max px-2 whitespace-pre", diffLineClass(diffLineKind(line)))}>
          {line || " "}
        </span>
      ))}
    </pre>
  );
}

function outputSummary(output: Record<string, unknown> | null): string | null {
  if (!output) return null;
  const stdout = textField(output, ["stdout"]);
  const stderr = textField(output, ["stderr"]);
  if (stdout || stderr) {
    return [stdout ? `stdout:\n${stdout}` : null, stderr ? `stderr:\n${stderr}` : null]
      .filter((value): value is string => value !== null)
      .join("\n");
  }
  const summary = textField(output, ["summary", "message", "result", "output"]);
  if (summary) return summary;
  const keys = Object.keys(output);
  const onlyToolInput = keys.every((key) => ["input", "tool_input", "toolInput", "tool_args", "args", "arguments"].includes(key));
  if (onlyToolInput) return null;
  const text = JSON.stringify(output, null, 2);
  return text === "{}" ? null : text;
}

function toolContextLabel(entry: TimelineEntry): string {
  return entry.toolName === "Bash" ? "Command context" : "Tool context";
}

function hasDrilldown(fields: DrilldownFields): boolean {
  return Boolean(
    fields.model ||
      fields.provider ||
      fields.command ||
      fields.tool_output ||
      fields.candidate_paths?.length ||
      fields.tool_context?.length ||
      fields.url_context?.length ||
      fields.patch_text ||
      fields.edit_before ||
      fields.edit_after ||
      fields.tool_input_json,
  );
}

function hasToolCallBody(entry: TimelineEntry, diffText: string | null): boolean {
  return Boolean(entry.command || entry.tool_output || diffText || entry.edit_before || entry.edit_after || entry.tool_input_json);
}

function missingToolCallBodyReason(entry: TimelineEntry): string | null {
  if (!entry.toolName) return null;
  if (entry.eventName !== "PreToolUse" && entry.eventName !== "PostToolUse") {
    return null;
  }
  return "Tool call body was not captured for this trace record. Newer traces include tool input when the harness exposes it; this historical row only has paths/findings metadata.";
}

function eventDrilldown(event: {
  model?: string | null;
  provider?: string | null;
  command?: string | null;
  tool_output?: string | null;
  candidate_paths?: string[];
  tool_input?: Record<string, unknown> | null;
}): DrilldownFields {
  return mergeDrilldown(
    {
      model: event.model,
      provider: event.provider,
      command: event.command,
      tool_output: event.tool_output,
      ...splitCandidateContext(event.candidate_paths),
    },
    toolInputDetailsFromInput(event.tool_input ?? null),
  );
}

function findNearbyDrilldown(
  events: Array<{
    timestamp: string;
    event_name: string;
    tool_name: string;
    model?: string | null;
    provider?: string | null;
    command?: string | null;
    tool_output?: string | null;
    candidate_paths?: string[];
    tool_input?: Record<string, unknown> | null;
  }>,
  timestamp: string,
  eventName: string,
  toolName: string,
): DrilldownFields {
  const target = Date.parse(timestamp);
  let best: DrilldownFields = {};
  let bestDistance = Number.POSITIVE_INFINITY;

  for (const event of events) {
    if (toolName && event.tool_name && event.tool_name !== toolName) continue;
    if (eventName === "PostToolUse") {
      if (event.event_name !== "PreToolUse" && event.event_name !== "PermissionRequest") {
        continue;
      }
    } else if (event.event_name !== eventName) {
      continue;
    }
    const distance = Math.abs(Date.parse(event.timestamp) - target);
    if (!Number.isFinite(distance) || distance > TOOL_DRILLDOWN_CORRELATION_WINDOW_MS) {
      continue;
    }
    const fields = eventDrilldown(event);
    if (!hasDrilldown(fields) || distance >= bestDistance) continue;
    best = fields;
    bestDistance = distance;
  }

  return best;
}

function mergeDrilldown(primary: DrilldownFields, fallback: DrilldownFields): DrilldownFields {
  return {
    model: primary.model ?? fallback.model,
    provider: primary.provider ?? fallback.provider,
    command: primary.command ?? fallback.command,
    tool_output: primary.tool_output ?? fallback.tool_output,
    tool_input_json: primary.tool_input_json ?? fallback.tool_input_json,
    patch_text: primary.patch_text ?? fallback.patch_text,
    edit_before: primary.edit_before ?? fallback.edit_before,
    edit_after: primary.edit_after ?? fallback.edit_after,
    candidate_paths: primary.candidate_paths?.length ? primary.candidate_paths : fallback.candidate_paths,
    tool_context: primary.tool_context?.length ? primary.tool_context : fallback.tool_context,
    url_context: primary.url_context?.length ? primary.url_context : fallback.url_context,
  };
}

function shortSessionId(sessionId: string): string {
  return sessionId.length > 16 ? `${sessionId.slice(0, 16)}…` : sessionId;
}

function lineageRoleLabel(role?: LineageRole | null): string {
  if (role === "child_mirror") return "child + mirror";
  if (!role || role === "raw") return "linked";
  return role;
}

function sourceLineageRoleFor(session: SessionData, source: LineageSource): LineageRole | null {
  if (source.lineage_role && source.lineage_role !== "parent" && source.lineage_role !== "raw") {
    return source.lineage_role;
  }
  if (source.session_id === session.id) return null;

  const childMatch = (session.childSessions ?? []).find((child) => child.id === source.session_id);
  const mirrorMatch = (session.mirrorSessions ?? []).find((mirror) => mirror.id === source.session_id);
  if (childMatch && mirrorMatch) return "child_mirror";
  if (childMatch) return childMatch.lineageRole ?? "child";
  if (mirrorMatch) return mirrorMatch.lineageRole ?? "mirror";

  const parentLinks = [source.parent_session_id, source.root_session_id];
  if (parentLinks.includes(session.id) || (session.rootSessionId && parentLinks.includes(session.rootSessionId))) {
    return source.origin_session_id ? "child_mirror" : "child";
  }
  if (source.origin_session_id === session.id || (session.rootSessionId && source.origin_session_id === session.rootSessionId)) {
    return "mirror";
  }
  return null;
}

function timelineSourceFields(session: SessionData, source: LineageSource): Pick<TimelineEntry, "sourceSessionId" | "sourceLineageRole"> {
  const sourceLineageRole = sourceLineageRoleFor(session, source);
  if (source.session_id === session.id && sourceLineageRole === null) return {};
  return { sourceSessionId: source.session_id, sourceLineageRole };
}

function isLinkedSource(session: SessionData, source: LineageSource): boolean {
  return source.session_id !== session.id || sourceLineageRoleFor(session, source) !== null;
}

function pickTimelineSource(session: SessionData, primary: LineageSource, fallback?: LineageSource): LineageSource {
  if (isLinkedSource(session, primary)) return primary;
  if (fallback && isLinkedSource(session, fallback)) return fallback;
  return primary;
}

function sourceOrigin(entry: TimelineEntry): SourceOrigin | null {
  if (!entry.sourceSessionId || entry.sourceSessionId === entry.sessionId) {
    return null;
  }
  return {
    roleLabel: lineageRoleLabel(entry.sourceLineageRole),
    sessionLabel: shortSessionId(entry.sourceSessionId),
    fullSessionId: entry.sourceSessionId,
  };
}

function formatAuditTime(timestamp: string | undefined): string {
  if (!timestamp) return "unknown";
  return new Date(timestamp).toLocaleTimeString();
}

function auditRows(entry: TimelineEntry): Array<[string, string]> {
  const origin = sourceOrigin(entry);
  const rows: Array<[string, string]> = [
    ["Grouped session", shortSessionId(entry.sessionId)],
    ["Platform", entry.platform ?? "unknown"],
    ["Event", entry.eventName ?? entry.label],
    ["Tool", entry.toolName || "session lifecycle"],
    ["Event time", formatAuditTime(entry.eventTime ?? entry.time)],
    ["Result time", formatAuditTime(entry.resultTime)],
    ["Decision", entry.decision ?? "n/a"],
    ["Findings", String(entry.findingCount ?? 0)],
    ["Errors", String(entry.errorCount ?? 0)],
  ];
  if (origin) {
    rows.splice(1, 0, ["Source session", origin.fullSessionId], ["Source role", origin.roleLabel]);
  }
  return rows;
}

function toggleSetValue<T>(selected: Set<T>, value: T): Set<T> {
  const next = new Set(selected);
  if (next.has(value)) next.delete(value);
  else next.add(value);
  return next;
}

function entryHasError(entry: TimelineEntry): boolean {
  return (entry.errorCount ?? 0) > 0 || entry.eventName === "PostToolUseFailure" || entry.decision === "deny" || entry.decision === "block";
}

function matchesDetailToggles(entry: TimelineEntry, detailToggles: Set<DetailToggle>): boolean {
  return (
    detailToggles.size === 0 ||
    (detailToggles.has("findings") && (entry.findingCount ?? 0) > 0) ||
    (detailToggles.has("errors") && entryHasError(entry))
  );
}

function matchesNestedFilters(
  entry: TimelineEntry,
  selectedEvents: Set<string>,
  selectedTools: Set<string>,
  selectedDecisions: Set<Decision>,
  detailToggles: Set<DetailToggle>,
): boolean {
  return (
    (selectedEvents.size === 0 || Boolean(entry.eventName && selectedEvents.has(entry.eventName))) &&
    (selectedTools.size === 0 || Boolean(entry.toolName && selectedTools.has(entry.toolName))) &&
    (selectedDecisions.size === 0 || Boolean(entry.decision && selectedDecisions.has(entry.decision))) &&
    matchesDetailToggles(entry, detailToggles)
  );
}

function eventDetail(event: HookEvent): string {
  const cp = splitCandidateContext(event.candidate_paths).candidate_paths ?? [];
  const pathInfo = cp.length > 0 ? ` → ${cp.join(", ")}` : "";
  return (event.tool_name ? `tool: ${event.tool_name}` : "session lifecycle") + pathInfo;
}

function resultDetail(result: HookResult): string {
  const errors = result.errors ?? [];
  return `${result.findings.length} findings, ${errors.length} errors`;
}

function timelineFindings(sessionId: string, resultIndex: number, findings: ResultFinding[]): TimelineFinding[] {
  return findings.map((finding, findingIndex) => ({
    id: `${sessionId}:result-finding:${resultIndex}:${findingIndex}:${finding.rule_id}`,
    ruleId: finding.rule_id,
    severity: finding.severity,
    decision: finding.decision,
    message: finding.message,
    additionalContext: finding.additional_context,
  }));
}

function findingSummary(finding: TimelineFinding): string {
  const decision = finding.decision ?? "context";
  const message = finding.message?.trim() || "No message provided.";
  return `${finding.severity} → ${decision}: ${message}`;
}

function isDuplicateFindingEntry(
  finding: {
    timestamp: string;
    tool_name: string;
    rule_id: string;
  },
  results: HookResult[],
): boolean {
  const findingTime = Date.parse(finding.timestamp);
  return results.some((result) => {
    if (result.tool_name !== finding.tool_name) return false;
    if (!result.findings.some((item) => item.rule_id === finding.rule_id)) {
      return false;
    }
    const distance = Math.abs(Date.parse(result.timestamp) - findingTime);
    return Number.isFinite(distance) && distance <= 5000;
  });
}

function entryTypeClass(type: TimelineEntry["type"]): string {
  if (type === "event" || type === "hook") return "bg-muted text-muted-foreground";
  if (type === "finding") return "bg-signal-ask/10 text-signal-ask";
  if (type === "result") return "bg-primary/10 text-primary";
  return "bg-signal-warn/10 text-signal-warn";
}

function findMatchingEvent(events: HookEvent[], claimedEventIndexes: Set<number>, result: HookResult): EventMatch | null {
  const resultTime = Date.parse(result.timestamp);
  let bestMatch: EventMatch | null = null;
  let bestDistance = Number.POSITIVE_INFINITY;

  for (const [index, event] of events.entries()) {
    if (claimedEventIndexes.has(index)) continue;
    if (event.event_name !== result.event_name) continue;
    if (event.tool_name !== result.tool_name) continue;
    const distance = Math.abs(Date.parse(event.timestamp) - resultTime);
    if (!Number.isFinite(distance) || distance > 5000) continue;
    if (distance >= bestDistance) continue;
    bestMatch = { event, index };
    bestDistance = distance;
  }

  return bestMatch;
}

export const SessionTimeline = memo(function SessionTimeline({ session }: { session: SessionData }) {
  const [page, setPage] = useState(0);
  const [agentOnly, setAgentOnly] = useState(false);
  const [openFilterMenu, setOpenFilterMenu] = useState<string | null>(null);
  const [selectedEntryId, setSelectedEntryId] = useState<string | null>(null);
  const [selectedEvents, setSelectedEvents] = useState<Set<string>>(() => new Set());
  const [selectedTools, setSelectedTools] = useState<Set<string>>(() => new Set());
  const [selectedDecisions, setSelectedDecisions] = useState<Set<Decision>>(() => new Set());
  const [detailToggles, setDetailToggles] = useState<Set<DetailToggle>>(() => new Set());

  const entries = useMemo(() => {
    const items: TimelineEntry[] = [];
    const eventContexts = [...session.events].sort((a, b) => a.timestamp.localeCompare(b.timestamp));
    const claimedEventIndexes = new Set<number>();

    for (const [resultIndex, r] of session.results.entries()) {
      const d = resolveDecision(r.findings);
      const matched = findMatchingEvent(session.events, claimedEventIndexes, r);
      const outputCommand = commandFromOutput(r.output);
      const outputText = outputSummary(r.output);
      const outputDetails = toolInputDetails(r.output);
      if (matched) {
        claimedEventIndexes.add(matched.index);
        const source = pickTimelineSource(session, matched.event, r);
        const drilldown = mergeDrilldown(mergeDrilldown(eventDrilldown(r), outputDetails), eventDrilldown(matched.event));
        items.push({
          id: `${session.id}:hook:${matched.index}:${resultIndex}:${matched.event.event_name}:${matched.event.timestamp}:${r.timestamp}:${matched.event.tool_name}`,
          time: r.timestamp > matched.event.timestamp ? r.timestamp : matched.event.timestamp,
          type: "hook",
          label: matched.event.event_name,
          detail: eventDetail(matched.event),
          sessionId: session.id,
          ...timelineSourceFields(session, source),
          platform: matched.event.platform,
          eventName: matched.event.event_name,
          toolName: matched.event.tool_name,
          eventTime: matched.event.timestamp,
          resultTime: r.timestamp,
          decision: d,
          resultLabel: `Result: ${d}`,
          resultDetail: resultDetail(r),
          findingCount: r.findings.length,
          errorCount: r.errors?.length ?? 0,
          findings: timelineFindings(session.id, resultIndex, r.findings),
          flagItemType: "result",
          flagItemId: `${session.id}:result:${r.timestamp}`,
          flagLabel: `${matched.event.event_name} result ${d} in session ${session.id.slice(0, 12)}`,
          ...drilldown,
          command: drilldown.command ?? r.command ?? outputCommand,
          tool_output: drilldown.tool_output ?? r.tool_output ?? outputText,
        });
        continue;
      }

      const fallback = findNearbyDrilldown(eventContexts, r.timestamp, r.event_name, r.tool_name);
      const drilldown = mergeDrilldown(mergeDrilldown(eventDrilldown(r), outputDetails), fallback);
      items.push({
        id: `${session.id}:result:${resultIndex}:${r.event_name}:${r.timestamp}:${r.tool_name}`,
        time: r.timestamp,
        type: "result",
        label: `Result: ${d}`,
        detail: resultDetail(r),
        sessionId: session.id,
        ...timelineSourceFields(session, r),
        platform: r.platform,
        eventName: r.event_name,
        toolName: r.tool_name,
        resultTime: r.timestamp,
        decision: d,
        findingCount: r.findings.length,
        errorCount: r.errors?.length ?? 0,
        findings: timelineFindings(session.id, resultIndex, r.findings),
        flagItemType: "result",
        flagItemId: `${session.id}:result:${r.timestamp}`,
        flagLabel: `Result ${d} in session ${session.id.slice(0, 12)}`,
        ...drilldown,
        command: drilldown.command ?? r.command ?? outputCommand,
        tool_output: drilldown.tool_output ?? r.tool_output ?? outputText,
      });
    }

    for (const [index, e] of session.events.entries()) {
      if (claimedEventIndexes.has(index)) continue;
      const drilldown = eventDrilldown(e);
      items.push({
        id: `${session.id}:event:${index}:${e.event_name}:${e.timestamp}:${e.tool_name}`,
        time: e.timestamp,
        type: "event",
        label: e.event_name,
        detail: eventDetail(e),
        sessionId: session.id,
        ...timelineSourceFields(session, e),
        platform: e.platform,
        eventName: e.event_name,
        toolName: e.tool_name,
        eventTime: e.timestamp,
        flagItemType: "event",
        flagItemId: `${session.id}:${e.event_name}:${e.timestamp}`,
        flagLabel: `${e.event_name} in session ${session.id.slice(0, 12)}`,
        ...drilldown,
      });
    }

    for (const [findingIndex, f] of session.findings.entries()) {
      if (isDuplicateFindingEntry(f, session.results)) continue;
      const msg = f.message ?? "";
      const dec = f.decision ?? "context";
      const fallback = findNearbyDrilldown(eventContexts, f.timestamp, f.event_name, f.tool_name);
      const drilldown = mergeDrilldown(eventDrilldown(f), fallback);
      items.push({
        id: `${session.id}:finding:${findingIndex}:${f.rule_id}:${f.timestamp}:${f.tool_name}`,
        time: f.timestamp,
        type: "finding",
        label: f.rule_id,
        detail: `${f.severity} → ${dec}: ${msg.slice(0, 80) || "(no message)"}`,
        sessionId: session.id,
        ...timelineSourceFields(session, f),
        platform: f.platform,
        eventName: f.event_name,
        toolName: f.tool_name,
        eventTime: f.timestamp,
        decision: dec,
        findingCount: 1,
        flagItemType: "finding",
        flagItemId: `${session.id}:${f.rule_id}:${f.timestamp}`,
        flagLabel: `${f.rule_id} (${f.severity} ${dec}) in session ${session.id.slice(0, 12)}`,
        ...drilldown,
      });
    }

    for (const [subprocessIndex, s] of session.subprocesses.entries()) {
      items.push({
        id: `${session.id}:subprocess:${subprocessIndex}:${s.timestamp}:${s.command}`,
        time: s.timestamp,
        type: "subprocess",
        label: s.command.slice(0, 40),
        detail: `exit ${s.returncode} (${s.duration_ms}ms)`,
        sessionId: session.id,
        ...timelineSourceFields(session, s),
        eventName: s.event_name,
        eventTime: s.timestamp,
        decision: s.returncode === 0 ? "allow" : "deny",
        flagItemType: "event",
        flagItemId: `${session.id}:subprocess:${s.timestamp}`,
        flagLabel: `${s.command.slice(0, 30)} (exit ${s.returncode}) in session ${session.id.slice(0, 12)}`,
        command: s.command,
        tool_output: (s.stdout ? `stdout:\n${s.stdout}` : "") + (s.stderr ? `\nstderr:\n${s.stderr}` : ""),
      });
    }

    return items.sort((a, b) => b.time.localeCompare(a.time));
  }, [session]);

  const filteredEntries = useMemo(() => {
    const nestedMatches = entries.filter((entry) =>
      matchesNestedFilters(entry, selectedEvents, selectedTools, selectedDecisions, detailToggles),
    );
    if (!agentOnly) return nestedMatches;
    return nestedMatches.filter((e) => {
      const isBlockOrDeny = e.decision === "block" || e.decision === "deny";
      const hasFindingsOrErrors = (e.findingCount ?? 0) > 0 || (e.errorCount ?? 0) > 0;
      if (isBlockOrDeny || hasFindingsOrErrors || e.type === "finding") {
        return true;
      }

      if (e.type === "event" || e.type === "hook") {
        return e.label === "PreToolUse" || e.label === "PostToolUse" || e.label === "PermissionRequest" || e.label === "PostToolUseFailure";
      }
      if (e.type === "result") {
        return !e.detail.startsWith("0 findings, 0 errors");
      }
      if (e.type === "subprocess") {
        return true;
      }
      return true;
    });
  }, [entries, selectedEvents, selectedTools, selectedDecisions, detailToggles, agentOnly]);

  const eventOptions = useMemo(() => [...new Set(entries.flatMap((entry) => entry.eventName ?? []))].sort(), [entries]);
  const toolOptions = useMemo(() => [...new Set(entries.flatMap((entry) => entry.toolName ?? []))].sort(), [entries]);
  const decisionOptions = useMemo(() => [...new Set(entries.flatMap((entry) => entry.decision ?? []))].sort(), [entries]);

  const resetNestedPaging = () => {
    setPage(0);
    setSelectedEntryId(null);
  };
  const activeFilters = useMemo(() => {
    const list: string[] = [];
    if (selectedEvents.size > 0) {
      list.push(`Event: ${[...selectedEvents].join(", ")}`);
    }
    if (selectedTools.size > 0) {
      list.push(`Tool: ${[...selectedTools].join(", ")}`);
    }
    if (selectedDecisions.size > 0) {
      list.push(`Decision: ${[...selectedDecisions].join(", ")}`);
    }
    if (detailToggles.has("findings")) {
      list.push("Has findings");
    }
    if (detailToggles.has("errors")) {
      list.push("Has errors");
    }
    if (agentOnly) {
      list.push("Agent actions only");
    }
    return list;
  }, [selectedEvents, selectedTools, selectedDecisions, detailToggles, agentOnly]);

  const clearAllFilters = () => {
    setSelectedEvents(new Set());
    setSelectedTools(new Set());
    setSelectedDecisions(new Set());
    setDetailToggles(new Set());
    setAgentOnly(false);
    resetNestedPaging();
  };
  const [metadataExpandedMap, setMetadataExpandedMap] = useState<Record<string, boolean>>({});

  const defaultSelection = useMemo(() => initialTimelineSelection(filteredEntries), [filteredEntries]);
  const activeEntryId = selectedEntryId ?? defaultSelection;

  const activeEntry = useMemo(() => {
    return filteredEntries.find((e) => e.id === activeEntryId);
  }, [filteredEntries, activeEntryId]);
  const pageCount = Math.max(1, Math.ceil(filteredEntries.length / PAGE_SIZE));
  const pageEntries = useMemo(() => {
    return filteredEntries.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
  }, [filteredEntries, page]);

  const pagePrimaryEntries = useMemo(
    () =>
      pageEntries.filter((e) => {
        const isLifecycleOnly = (e.type === "event" || e.type === "result") && (e.findingCount ?? 0) === 0 && (e.errorCount ?? 0) === 0;
        return !isLifecycleOnly;
      }),
    [pageEntries],
  );

  const pageUnmatchedEntries = useMemo(
    () =>
      pageEntries.filter((e) => {
        const isLifecycleOnly = (e.type === "event" || e.type === "result") && (e.findingCount ?? 0) === 0 && (e.errorCount ?? 0) === 0;
        return isLifecycleOnly;
      }),
    [pageEntries],
  );

  const renderTimelineRow = (entry: TimelineEntry, index: number, isUnmatched = false) => {
    const isSelected = activeEntryId === entry.id;
    const rowSummary = timelineRowSummary(entry);

    const deEmphasize =
      isUnmatched ||
      ((entry.type === "event" || entry.type === "result") && (entry.findingCount ?? 0) === 0 && (entry.errorCount ?? 0) === 0);

    return (
      <div
        key={entry.id}
        className={cn(
          "relative flex flex-col mb-3 last:mb-0 group border-b border-border/10 pb-2 transition-all duration-150 animate-in fade-in slide-in-from-bottom-1 fill-mode-both",
          deEmphasize && "opacity-60 hover:opacity-100",
          isSelected && "bg-primary/5 rounded px-2 -mx-2 border-primary/20",
        )}
        style={{
          animationDelay: `${index * 15}ms`,
          animationFillMode: "both",
        }}
      >
        <button
          type="button"
          aria-label={`${entry.type} ${entry.label} ${entry.resultLabel ?? ""}`.trim()}
          aria-expanded={isSelected}
          className={cn(
            "relative flex w-full cursor-pointer items-start gap-3 rounded p-1.5 pr-9 text-left transition-all duration-150 ease-out-quint hover:bg-muted/15 active:scale-[0.985] focus:outline-none focus:ring-1 focus:ring-primary/50",
            isSelected && "bg-primary/10 ring-1 ring-primary/30",
          )}
          onClick={() => {
            setSelectedEntryId(entry.id);
          }}
        >
          <div className="absolute left-0 top-3 z-10 flex items-center justify-center">
            {entry.decision === "block" || entry.decision === "deny" ? (
              <AlertOctagon className="w-3.5 h-3.5 text-signal-deny fill-signal-deny/10" />
            ) : entry.decision === "ask" || entry.decision === "warn" || entry.decision === "context" ? (
              <ShieldAlert className="w-3.5 h-3.5 text-signal-ask fill-signal-ask/10" />
            ) : entry.decision === "allow" ? (
              <CheckCircle2 className="w-3.5 h-3.5 text-signal-allow fill-signal-allow/10" />
            ) : (
              <Info className="w-3.5 h-3.5 text-muted-foreground" />
            )}
          </div>

          <div className="ml-5 min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <span className={cn("text-[9px] uppercase px-1 py-0.5 rounded font-bold tracking-wider", entryTypeClass(entry.type))}>
                {entry.type}
              </span>
              <span className="text-xs font-semibold truncate">{rowSummary.title}</span>
              <div className="ml-auto flex shrink-0 items-center gap-1.5">
                <span className="text-[9px] text-muted-foreground">{new Date(entry.time).toLocaleTimeString()}</span>
              </div>
            </div>
            <div className="text-[10px] text-muted-foreground mt-0.5 truncate font-mono">{rowSummary.subtitle}</div>
          </div>
        </button>
        <div className="absolute right-2 top-2 z-20">
          <FlagButton itemType={entry.flagItemType} itemId={entry.flagItemId} label={entry.flagLabel} compact />
        </div>

        {isSelected && <div className="md:hidden mt-2 pl-4">{renderDetailPane(entry)}</div>}
      </div>
    );
  };

  const renderDetailPane = (entry: TimelineEntry) => {
    const diffPayload = focusedEditPayload(entry);
    const missingBodyReason = hasToolCallBody(entry, diffPayload?.prettyText ?? null) ? null : missingToolCallBodyReason(entry);

    const hasMeaningfulEvidence = Boolean(
      entry.command ||
        entry.tool_output ||
        (entry.findings && entry.findings.length > 0) ||
        entry.edit_before ||
        entry.edit_after ||
        entry.tool_input_json,
    );

    const isMetaExpanded = metadataExpandedMap[entry.id] ?? !hasMeaningfulEvidence;
    const corrStatus = correlationStatus(entry);

    return (
      <div
        key={entry.id}
        className="bg-muted/15 border border-border/20 p-3 rounded text-[11px] space-y-3 font-sans transition-all duration-300 ease-out-expo animate-in fade-in slide-in-from-right-4"
      >
        <TimelineVerdictStrip entry={entry} />

        {entry.candidate_paths && entry.candidate_paths.length > 0 && (
          <div className="font-mono">
            <span className="text-muted-foreground select-none">File(s): </span>
            <span className="text-foreground break-all">{entry.candidate_paths.join(", ")}</span>
          </div>
        )}

        {entry.tool_context && entry.tool_context.length > 0 && (
          <div className="font-mono">
            <span className="text-muted-foreground select-none">{toolContextLabel(entry)}: </span>
            <span className="text-foreground break-all">{entry.tool_context.join(", ")}</span>
          </div>
        )}

        {entry.url_context && entry.url_context.length > 0 && (
          <div className="font-mono">
            <span className="text-muted-foreground select-none">URL(s): </span>
            <span className="text-foreground break-all">{entry.url_context.join(", ")}</span>
          </div>
        )}

        {entry.findings && entry.findings.length > 0 && (
          <div className="space-y-1.5">
            <span className="text-muted-foreground font-semibold">Grouped finding(s):</span>
            <div className="space-y-1.5">
              {entry.findings.map((finding) => (
                <div key={finding.id} className="rounded border border-signal-ask/20 bg-signal-ask/5 p-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded bg-signal-ask/10 px-1 py-0.5 uppercase text-signal-ask font-bold text-[9px]">Finding</span>
                    <span className="font-bold text-foreground text-[10px]">{finding.ruleId}</span>
                  </div>
                  <div className="mt-1 text-muted-foreground font-mono">{findingSummary(finding)}</div>
                  {finding.additionalContext && <FindingEvidenceBlock text={finding.additionalContext} />}
                </div>
              ))}
            </div>
          </div>
        )}

        {(entry.model || entry.provider) && (
          <div className="font-mono text-muted-foreground">
            AI Model: <span className="text-foreground font-semibold">{entry.model || "Unknown"}</span> ({entry.provider || "Unknown"})
          </div>
        )}

        {entry.command && <PayloadPanel title="Command" pretty={<CodeBlock text={entry.command} />} rawText={entry.command} />}

        {diffPayload && (
          <PayloadPanel title="Patch / focused diff" pretty={<DiffPreview text={diffPayload.prettyText} />} rawText={diffPayload.rawText} />
        )}

        {(entry.edit_before || entry.edit_after) && (
          <div className="space-y-1">
            <span className="text-muted-foreground font-semibold">Focused edit:</span>
            <div className="grid gap-2 md:grid-cols-2">
              {entry.edit_before && (
                <div className="min-w-0">
                  <div className="mb-1 text-muted-foreground text-[9px] uppercase tracking-wider">Before</div>
                  <pre className="max-h-48 max-w-full overflow-auto rounded border border-border/20 bg-background/50 p-2 text-foreground font-mono whitespace-pre-wrap">
                    {entry.edit_before}
                  </pre>
                </div>
              )}
              {entry.edit_after && (
                <div className="min-w-0">
                  <div className="mb-1 text-muted-foreground text-[9px] uppercase tracking-wider">After</div>
                  <pre className="max-h-48 max-w-full overflow-auto rounded border border-border/20 bg-background/50 p-2 text-foreground font-mono whitespace-pre-wrap">
                    {entry.edit_after}
                  </pre>
                </div>
              )}
            </div>
          </div>
        )}

        {entry.tool_input_json && (
          <PayloadPanel
            title="Tool input"
            pretty={<PrettyJsonView text={entry.tool_input_json} compactPatchText />}
            rawText={entry.tool_input_json}
          />
        )}

        {entry.tool_output && (
          <PayloadPanel title="Output" pretty={<PrettyOutputView text={entry.tool_output} />} rawText={entry.tool_output} />
        )}

        {missingBodyReason && (
          <div className="rounded border border-signal-warn/20 bg-signal-warn/5 p-2.5 text-signal-warn">
            <div className="mb-1 text-[9px] uppercase tracking-wider font-semibold text-muted-foreground">
              {corrStatus === "historical-missing-input" ? "Historical Trace Limitation" : "Tool input unavailable"}
            </div>
            <div className="text-foreground">{missingBodyReason}</div>
          </div>
        )}

        {!hasDrilldown(entry) && entry.type !== "hook" && (
          <div className="text-muted-foreground italic">No correlated drill-down data available for this entry.</div>
        )}

        <div className="border border-border/20 rounded bg-background/30 overflow-hidden mt-3">
          <button
            type="button"
            onClick={() =>
              setMetadataExpandedMap((curr) => ({
                ...curr,
                [entry.id]: !isMetaExpanded,
              }))
            }
            className="w-full flex items-center justify-between px-3 py-1.5 bg-muted/20 hover:bg-muted/30 text-[9px] text-muted-foreground uppercase font-bold tracking-wider"
          >
            <span>Trace Metadata</span>
            <span>{isMetaExpanded ? "Hide" : "Show"}</span>
          </button>
          {isMetaExpanded && (
            <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 p-3 font-mono border-t border-border/10 text-[10px]">
              {auditRows(entry).map(([label, value]) => (
                <div key={label} className="min-w-0">
                  <span className="text-muted-foreground select-none">{label}: </span>
                  <span className="text-foreground break-all">{value}</span>
                </div>
              ))}
              <div className="min-w-0 col-span-2 mt-1 pt-1 border-t border-border/10">
                <span className="text-muted-foreground select-none">Correlation Status: </span>
                <span className="text-foreground font-bold capitalize">{corrStatus}</span>
              </div>
            </div>
          )}
        </div>
      </div>
    );
  };

  const renderPagination = () => (
    <div className="flex items-center justify-between px-4 py-2 border-t border-border text-[10px] text-muted-foreground sticky bottom-0 bg-background/95 backdrop-blur-sm">
      <span>{filteredEntries.length} entries total</span>
      <div className="flex gap-2">
        <button
          type="button"
          disabled={page === 0}
          onClick={() => setPage((p) => p - 1)}
          className="hover:text-foreground disabled:opacity-30"
        >
          ← Prev
        </button>
        <span>
          {page + 1} / {pageCount}
        </span>
        <button
          type="button"
          disabled={page + 1 >= pageCount}
          onClick={() => setPage((p) => p + 1)}
          className="hover:text-foreground disabled:opacity-30"
        >
          Next →
        </button>
      </div>
    </div>
  );

  return (
    <div className="flex h-[600px] min-w-0 w-full flex-col overflow-hidden border-t border-border bg-background/50">
      <div className="flex flex-col gap-2 px-4 py-2 border-b border-border bg-background/30 text-xs">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <span className="text-muted-foreground font-medium">Timeline Log</span>
          <label className="flex items-center gap-1.5 cursor-pointer text-[10px] text-muted-foreground hover:text-foreground select-none">
            <input
              type="checkbox"
              checked={agentOnly}
              onChange={(e) => {
                setAgentOnly(e.target.checked);
                resetNestedPaging();
              }}
              className="rounded border-border text-primary focus:ring-primary h-3 w-3"
            />
            Agent actions only
          </label>
        </div>
        <div className="flex flex-wrap gap-x-4 gap-y-1.5 text-[10px]">
          <NestedFilterGroup label="Event">
            <NestedMultiSelectMenu
              menuId="event"
              openMenuId={openFilterMenu}
              setOpenMenuId={setOpenFilterMenu}
              options={eventOptions}
              selected={selectedEvents}
              onToggle={(eventName) => {
                setSelectedEvents((current) => toggleSetValue(current, eventName));
                resetNestedPaging();
              }}
            />
          </NestedFilterGroup>
          <NestedFilterGroup label="Tool">
            <NestedMultiSelectMenu
              menuId="tool"
              openMenuId={openFilterMenu}
              setOpenMenuId={setOpenFilterMenu}
              options={toolOptions}
              selected={selectedTools}
              onToggle={(toolName) => {
                setSelectedTools((current) => toggleSetValue(current, toolName));
                resetNestedPaging();
              }}
            />
          </NestedFilterGroup>
          <NestedFilterGroup label="Decision">
            <NestedMultiSelectMenu
              menuId="decision"
              openMenuId={openFilterMenu}
              setOpenMenuId={setOpenFilterMenu}
              options={decisionOptions}
              selected={selectedDecisions}
              onToggle={(decision) => {
                setSelectedDecisions((current) => toggleSetValue(current, decision));
                resetNestedPaging();
              }}
            />
          </NestedFilterGroup>
          <NestedFilterGroup label="Rows">
            {DETAIL_TOGGLES.map((toggle) => (
              <NestedFilterChip
                key={toggle}
                active={detailToggles.has(toggle)}
                onClick={() => {
                  setDetailToggles((current) => toggleSetValue(current, toggle));
                  resetNestedPaging();
                }}
              >
                {DETAIL_TOGGLE_LABELS[toggle]}
              </NestedFilterChip>
            ))}
          </NestedFilterGroup>
          {activeFilters.length > 0 && (
            <div className="flex flex-wrap items-center justify-between gap-2 mt-1.5 pt-1.5 border-t border-border/10 text-[10px]">
              <div className="flex items-center gap-1.5 text-muted-foreground">
                <span className="font-semibold select-none">Active Filters:</span>
                <span className="text-foreground">{activeFilters.join(" | ")}</span>
              </div>
              <button
                type="button"
                onClick={clearAllFilters}
                className="flex items-center gap-1 text-primary hover:text-primary-foreground font-medium transition-colors"
              >
                <FilterX className="w-3 h-3" />
                Clear timeline filters
              </button>
            </div>
          )}
        </div>
      </div>

      <div className="flex flex-1 min-h-0 md:flex-row flex-col overflow-hidden">
        <div className="flex-[4] flex flex-col min-w-0 border-r border-border/40 overflow-y-auto pr-1">
          <div className="p-4 pl-10 relative">
            <div className="absolute left-[21px] top-6 bottom-6 w-px bg-border" />

            {pagePrimaryEntries.map((entry, idx) => renderTimelineRow(entry, idx))}

            {pageUnmatchedEntries.length > 0 && (
              <div className="mt-4">
                <h4 className="text-[9px] text-muted-foreground uppercase tracking-wider mb-2 font-bold pl-1.5">
                  Unmatched trace events ({pageUnmatchedEntries.length})
                </h4>
                {pageUnmatchedEntries.map((entry, idx) => renderTimelineRow(entry, pagePrimaryEntries.length + idx, true))}
              </div>
            )}

            {pageEntries.length === 0 && (
              <div className="rounded border border-border/30 bg-muted/10 px-3 py-4 text-center text-[10px] text-muted-foreground">
                No timeline entries match the current filters.
              </div>
            )}
          </div>

          {pageCount > 1 && renderPagination()}
        </div>

        <div className="hidden md:flex flex-[6] flex-col min-w-0 bg-background/25 overflow-y-auto p-4 sticky top-0 border-l border-border/20">
          {activeEntry ? (
            renderDetailPane(activeEntry)
          ) : (
            <div className="flex flex-col items-center justify-center h-full text-muted-foreground italic text-xs">
              Select an event from the timeline to view details.
            </div>
          )}
        </div>
      </div>
    </div>
  );
});

function NestedFilterGroup({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="text-muted-foreground">{label}:</span>
      {children}
    </div>
  );
}

function NestedFilterChip({ active, onClick, children }: { active: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded border px-1.5 py-0.5 transition-all duration-150 ease-out-quint active:scale-95",
        active
          ? "border-primary/40 bg-primary/15 text-primary"
          : "border-border/40 bg-muted/20 text-muted-foreground hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}

function NestedMultiSelectMenu<T extends string>({
  menuId,
  openMenuId,
  setOpenMenuId,
  options,
  selected,
  onToggle,
}: {
  menuId: string;
  openMenuId: string | null;
  setOpenMenuId: (menuId: string | null) => void;
  options: T[];
  selected: Set<T>;
  onToggle: (option: T) => void;
}) {
  const isOpen = openMenuId === menuId;
  const selectionLabel = selected.size === 0 ? "All" : `${selected.size} selected`;
  const triggerRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpenMenuId(null);
        triggerRef.current?.focus();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, setOpenMenuId]);

  return (
    <div className="relative">
      <button
        type="button"
        ref={triggerRef}
        onClick={() => setOpenMenuId(isOpen ? null : menuId)}
        className={cn(
          "rounded border px-1.5 py-0.5 transition-all duration-150 ease-out-quint active:scale-95",
          selected.size > 0 || isOpen
            ? "border-primary/40 bg-primary/15 text-primary"
            : "border-border/40 bg-muted/20 text-muted-foreground hover:text-foreground",
        )}
      >
        {selectionLabel}
      </button>
      {isOpen && (
        <div className="absolute left-0 top-full z-30 mt-1 min-w-44 rounded border border-border bg-popover p-2 shadow-lg animate-in fade-in slide-in-from-top-1 duration-150 ease-out-quint">
          <div className="mb-1 text-[9px] uppercase tracking-wider text-muted-foreground">Options</div>
          <div className="max-h-48 space-y-1 overflow-y-auto">
            {options.map((option) => (
              <label
                key={option}
                className="flex cursor-pointer items-center gap-2 rounded px-1 py-0.5 text-muted-foreground hover:bg-muted/20 hover:text-foreground"
              >
                <input
                  type="checkbox"
                  checked={selected.has(option)}
                  onChange={() => onToggle(option)}
                  className="h-3 w-3 rounded border-border text-primary focus:ring-primary"
                />
                <span>{option}</span>
              </label>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
