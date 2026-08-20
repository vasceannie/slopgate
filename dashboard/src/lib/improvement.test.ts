import { readdirSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { coerceTraceRecord } from "@/context/traceRecordValidation";
import type { HookResult } from "@/types/slopgate";
import { buildImprovementFixtureSummary } from "./improvement";

const FIXTURE_DIRECTORY = resolve(dirname(fileURLToPath(import.meta.url)), "../../../tests/fixtures/improvement");
const FIXTURE_FILES = readdirSync(FIXTURE_DIRECTORY)
  .filter((fileName) => fileName.endsWith(".json"))
  .sort();

function isObjectRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function loadFixture(fileName: string): { entries: Record<string, unknown>[]; expected: Record<string, unknown> } {
  const payload: unknown = JSON.parse(readFileSync(resolve(FIXTURE_DIRECTORY, fileName), "utf8"));
  if (!isObjectRecord(payload) || !Array.isArray(payload.entries) || !isObjectRecord(payload.expected)) {
    throw new Error(`invalid shared improvement fixture: ${fileName}`);
  }
  const entries = payload.entries.filter(isObjectRecord);
  if (entries.length !== payload.entries.length) {
    throw new Error(`shared improvement fixture contains a non-object entry: ${fileName}`);
  }
  return { entries, expected: payload.expected };
}

function normalizeResults(entries: Record<string, unknown>[]): HookResult[] {
  const results: HookResult[] = [];
  for (const entry of entries) {
    const accepted = coerceTraceRecord(entry);
    if (accepted?.type !== "result") {
      throw new Error("shared improvement fixture entry did not normalize as a result");
    }
    results.push(accepted.record);
  }
  return results;
}

describe("dashboard improvement evaluator parity", () => {
  it("loads the complete shared fixture suite", () => {
    expect(FIXTURE_FILES).toHaveLength(11);
  });

  it.each(FIXTURE_FILES)("matches the canonical Python contract for %s", (fileName) => {
    const fixture = loadFixture(fileName);

    const summary = buildImprovementFixtureSummary(normalizeResults(fixture.entries));

    expect(summary).toEqual(fixture.expected);
  });
});
