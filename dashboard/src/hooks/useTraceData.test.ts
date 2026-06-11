import { describe, expect, it } from "vitest";
import type { RuleFinding } from "@/types/slopgate";
import {
	streamSchemaValidationWarning,
	summarizeTopRules,
} from "./useTraceData";

function finding(
	rule_id: string,
	decision: RuleFinding["decision"],
): RuleFinding {
	return {
		timestamp: "2026-05-27T12:00:00.000Z",
		platform: "opencode",
		event_name: "Stop",
		session_id: `session-${rule_id}-${decision ?? "none"}`,
		tool_name: "Stop",
		rule_id,
		severity: "LOW",
		decision,
		message: `${rule_id} ${decision ?? "none"}`,
		additional_context: null,
		metadata: {},
	};
}

describe("trace top-rule summaries", () => {
	it("prioritizes enforcement deny/block rules ahead of enrichment noise", () => {
		const rules = [
			finding("ENRICHMENT", "context"),
			finding("ENRICHMENT", "context"),
			finding("ENRICHMENT", "context"),
			finding("_ENRICHMENT_METRICS", "info"),
			finding("PY-CODE-018", "block"),
			finding("PY-CODE-013", "deny"),
		];

		const topRules = summarizeTopRules(rules);

		expect(topRules.map((rule) => rule.rule_id)).toEqual([
			"PY-CODE-018",
			"PY-CODE-013",
			"ENRICHMENT",
			"_ENRICHMENT_METRICS",
		]);
		expect(
			topRules.find((rule) => rule.rule_id === "ENRICHMENT"),
		).toMatchObject({ count: 3, decisions: { context: 3 } });
		expect(
			topRules.find((rule) => rule.rule_id === "_ENRICHMENT_METRICS"),
		).toMatchObject({ count: 1, decisions: { info: 1 } });
	});

	it("preserves raw advisory telemetry when no enforcement findings exist", () => {
		const rules = [
			finding("ENRICHMENT", "context"),
			finding("PY-CODE-012", "context"),
			finding("PY-CODE-012", "context"),
			finding("_ENRICHMENT_METRICS", "info"),
		];

		const topRules = summarizeTopRules(rules);

		expect(topRules.map((rule) => rule.rule_id)).toEqual([
			"PY-CODE-012",
			"ENRICHMENT",
			"_ENRICHMENT_METRICS",
		]);
		expect(topRules).toHaveLength(3);
	});

	it("keeps high-volume advisory rules available after enforcement-heavy sorting", () => {
		const rules = Array.from({ length: 26 }, (_unused, index) =>
			finding(`PY-BLOCK-${index}`, "deny"),
		);
		rules.push(
			...Array.from({ length: 50 }, () =>
				finding("ADVISORY-HOTSPOT", "context"),
			),
		);

		const topRules = summarizeTopRules(rules);

		expect(
			topRules.find((rule) => rule.rule_id === "ADVISORY-HOTSPOT"),
		).toMatchObject({
			count: 50,
			decisions: { context: 50 },
		});
	});
});

describe("stream schema validation warning", () => {
	it("does not warn when the live stream is accepting records", () => {
		expect(streamSchemaValidationWarning(8, 254852)).toBeNull();
	});

	it("warns when stream records are rejected before any record is accepted", () => {
		expect(streamSchemaValidationWarning(2, 0)).toBe(
			"2 streamed records failed dashboard schema validation.",
		);
	});
});
