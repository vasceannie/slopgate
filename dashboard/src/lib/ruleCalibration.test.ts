import { describe, expect, it } from "vitest";
import { computeCalibrationSignals } from "./ruleCalibration";
import type { RuleFinding, HookResult } from "@/types/slopgate";

function createFinding(ruleId: string, decision: RuleFinding["decision"], sessionId = "session-1"): RuleFinding {
	return {
		timestamp: "2026-06-14T12:00:00.000Z",
		platform: "opencode",
		event_name: "Stop",
		session_id: sessionId,
		tool_name: "Stop",
		rule_id: ruleId,
		severity: "HIGH",
		decision,
		message: `${ruleId} fired`,
		additional_context: null,
		metadata: {},
	};
}

describe("rule calibration scorer", () => {
	it("classifies advisory/context rules followed by allow as advisory pressure", () => {
		// Arrange: advisory rule context/warn followed by allow in session
		const rules = [
			createFinding("PY-LOG-002", "context", "session-1"),
			createFinding("PY-LOG-002", "warn", "session-2"),
		];
		const results: HookResult[] = [
			{
				timestamp: "2026-06-14T12:00:01.000Z",
				platform: "opencode",
				event_name: "PostToolUse",
				session_id: "session-1",
				tool_name: "Stop",
				findings: [{ rule_id: "PY-LOG-002", severity: "HIGH", decision: "context", message: "fired" }],
				errors: null,
				output: null,
			},
			{
				timestamp: "2026-06-14T12:00:02.000Z",
				platform: "opencode",
				event_name: "PostToolUse",
				session_id: "session-2",
				tool_name: "Stop",
				findings: [{ rule_id: "PY-LOG-002", severity: "HIGH", decision: "warn", message: "fired" }],
				errors: null,
				output: null,
			},
		];

		// Act
		const signals = computeCalibrationSignals(rules, results);

		// Assert
		const signal = signals.find(s => s.rule_id === "PY-LOG-002");
		expect(signal).toBeDefined();
		expect(signal?.advisoryPressure).toBeGreaterThan(0);
		expect(signal?.isAdvisorySuspect).toBe(true);
	});

	it("computes repeat-fire triage score from repeated occurrences, intensity, and breadth", () => {
		// Arrange: rule PY-CODE-010 fires in 2 distinct runs in session-1 (multi-warn), and 1 run in session-2 (single-warn)
		const rules = [
			{ ...createFinding("PY-CODE-010", "warn", "session-1"), timestamp: "2026-06-14T12:00:01.000Z" },
			{ ...createFinding("PY-CODE-010", "warn", "session-1"), timestamp: "2026-06-14T12:00:02.000Z" },
			{ ...createFinding("PY-CODE-010", "warn", "session-2"), timestamp: "2026-06-14T12:00:01.000Z" },
		];
		const results: HookResult[] = [];

		// Act
		const signals = computeCalibrationSignals(rules, results);

		// Assert
		const signal = signals.find((s) => s.rule_id === "PY-CODE-010");
		expect(signal).toBeDefined();
		expect(signal?.runtimeErrorPressure).toBe(25); // 50% repeat rate with low volume/breadth should not look saturated
		expect(signal?.repeatFireSessions).toBe(1);
		expect(signal?.isRuntimeErrorSuspect).toBe(false);
	});

	it("ranks all-repeat-fire rules by volume and breadth instead of flattening at 100", () => {
		// Arrange: both rules repeat in every active session, but HIGH-VOLUME has broader evidence.
		const lowVolumeRules = [
			{ ...createFinding("LOW-VOLUME", "warn", "low-session"), timestamp: "2026-06-14T12:00:01.000Z" },
			{ ...createFinding("LOW-VOLUME", "warn", "low-session"), timestamp: "2026-06-14T12:00:02.000Z" },
		];
		const highVolumeRules = Array.from({ length: 10 }, (_, sessionIndex) => {
			return Array.from({ length: 5 }, (_, findingIndex) => ({
				...createFinding("HIGH-VOLUME", "warn", `high-session-${sessionIndex}`),
				timestamp: `2026-06-14T12:${String(sessionIndex).padStart(2, "0")}:${String(findingIndex).padStart(2, "0")}.000Z`,
			}));
		}).flat();
		const rules = [...lowVolumeRules, ...highVolumeRules];

		// Act
		const signals = computeCalibrationSignals(rules, []);

		// Assert
		const lowVolume = signals.find((s) => s.rule_id === "LOW-VOLUME");
		const highVolume = signals.find((s) => s.rule_id === "HIGH-VOLUME");
		expect(lowVolume?.runtimeErrorPressure).toBeLessThan(100);
		expect(highVolume?.runtimeErrorPressure).toBeLessThan(100);
		expect(highVolume?.runtimeErrorPressure).toBeGreaterThan(lowVolume?.runtimeErrorPressure ?? 0);
	});

	it("classifies unparseable error strings as generic/none instead of assigning to substring rules", () => {
		// Arrange: a generic error containing "PY-CODE" but not matching "RULE: message" format
		const rules = [createFinding("PY-CODE-010", "block", "session-1")];
		const results: HookResult[] = [
			{
				timestamp: "2026-06-14T12:00:01.000Z",
				platform: "opencode",
				event_name: "PostToolUse",
				session_id: "session-error",
				tool_name: "Stop",
				findings: [],
				errors: ["some random crash output containing PY-CODE-010 but not prefixed"],
				output: null,
			},
		];

		// Act
		const signals = computeCalibrationSignals(rules, results);

		// Assert
		const signal = signals.find(s => s.rule_id === "PY-CODE-010");
		expect(signal?.runtimeErrorCount).toBe(0);
		expect(signal?.runtimeErrorPressure).toBe(0);
	});

	it("marks parseable runtime-error-only rules as review-worthy", () => {
		// Arrange: a rule can fail during runtime before producing findings.
		const results: HookResult[] = [
			{
				timestamp: "2026-06-14T12:00:01.000Z",
				platform: "opencode",
				event_name: "PostToolUse",
				session_id: "session-error",
				tool_name: "Stop",
				findings: [],
				errors: ["PY-CODE-010: detector crashed before emitting findings"],
				output: null,
			},
		];

		// Act
		const signals = computeCalibrationSignals([], results);

		// Assert
		const signal = signals.find((s) => s.rule_id === "PY-CODE-010");
		expect(signal).toBeDefined();
		expect(signal?.runtimeErrorCount).toBe(1);
		expect(signal?.runtimeErrorPressure).toBe(43);
		expect(signal?.isRuntimeErrorSuspect).toBe(true);
		expect(signal?.isClean).toBe(false);
	});

	it("does not corrupt clean counts when overlapping signals are present", () => {
		// Arrange: rule with both high advisory pressure and variable decisions
		// It should be both isAdvisorySuspect and isVariableSuspect, and NOT isClean.
		const rules = [
			{ ...createFinding("PY-CODE-013", "allow", "session-1"), timestamp: "2026-06-14T12:00:01.000Z" },
			{ ...createFinding("PY-CODE-013", "block", "session-2"), timestamp: "2026-06-14T12:00:02.000Z" },
			{ ...createFinding("PY-CODE-013", "warn", "session-3"), timestamp: "2026-06-14T12:00:03.000Z" },
			{ ...createFinding("PY-CODE-013", "warn", "session-4"), timestamp: "2026-06-14T12:00:04.000Z" },
			{ ...createFinding("PY-CODE-013", "warn", "session-5"), timestamp: "2026-06-14T12:00:05.000Z" },
		];
		// Make sessions 3, 4, 5 allowed overall to trigger advisory allowed-after-warn
		const results: HookResult[] = [
			{
				timestamp: "2026-06-14T12:00:01.000Z",
				platform: "opencode",
				event_name: "PostToolUse",
				session_id: "session-1",
				tool_name: "Stop",
				findings: [{ rule_id: "PY-CODE-013", severity: "HIGH", decision: "allow", message: "fired" }],
				errors: null,
				output: null,
			},
			{
				timestamp: "2026-06-14T12:00:02.000Z",
				platform: "opencode",
				event_name: "PostToolUse",
				session_id: "session-2",
				tool_name: "Stop",
				findings: [{ rule_id: "PY-CODE-013", severity: "HIGH", decision: "block", message: "fired" }],
				errors: null,
				output: null,
			},
			{
				timestamp: "2026-06-14T12:00:03.000Z",
				platform: "opencode",
				event_name: "PostToolUse",
				session_id: "session-3",
				tool_name: "Stop",
				findings: [{ rule_id: "PY-CODE-013", severity: "HIGH", decision: "warn", message: "fired" }],
				errors: null,
				output: null,
			},
			{
				timestamp: "2026-06-14T12:00:04.000Z",
				platform: "opencode",
				event_name: "PostToolUse",
				session_id: "session-4",
				tool_name: "Stop",
				findings: [{ rule_id: "PY-CODE-013", severity: "HIGH", decision: "warn", message: "fired" }],
				errors: null,
				output: null,
			},
			{
				timestamp: "2026-06-14T12:00:05.000Z",
				platform: "opencode",
				event_name: "PostToolUse",
				session_id: "session-5",
				tool_name: "Stop",
				findings: [{ rule_id: "PY-CODE-013", severity: "HIGH", decision: "warn", message: "fired" }],
				errors: null,
				output: null,
			},
		];

		// Act
		const signals = computeCalibrationSignals(rules, results);

		// Assert
		const signal = signals.find(s => s.rule_id === "PY-CODE-013");
		expect(signal).toBeDefined();
		expect(signal?.isAdvisorySuspect).toBe(true);
		expect(signal?.isVariableSuspect).toBe(true);
		expect(signal?.isClean).toBe(false);
	});

	it("assigns low confidence to small sample rules", () => {
		// Arrange: rule with only 1 finding
		const rules = [createFinding("PY-CODE-012", "context", "session-1")];
		const results: HookResult[] = [];

		// Act
		const signals = computeCalibrationSignals(rules, results);

		// Assert
		const signal = signals.find(s => s.rule_id === "PY-CODE-012");
		expect(signal).toBeDefined();
		expect(signal?.confidence).toBe("low");
	});

	it("computes delivered persistence from comparable hook results", () => {
		// Arrange:
		// session-1: PY-CODE-010 is delivered at 12:00:01 but absent from a comparable later result (resolved).
		// session-2: PY-CODE-010 is delivered at 12:00:01; an unrelated later result must not count as resolution.
		const rules = [
			{ ...createFinding("PY-CODE-010", "warn", "session-1"), timestamp: "2026-06-14T12:00:01.000Z" },
			{ ...createFinding("PY-CODE-010", "warn", "session-2"), timestamp: "2026-06-14T12:00:01.000Z" },
		];
		const results: HookResult[] = [
			{
				timestamp: "2026-06-14T12:00:01.000Z",
				platform: "opencode",
				event_name: "PostToolUse",
				session_id: "session-1",
				tool_name: "Stop",
				findings: [{ rule_id: "PY-CODE-010", severity: "HIGH", decision: "warn", message: "fired" }],
				errors: null,
				output: null,
			},
			{
				timestamp: "2026-06-14T12:00:02.000Z", // later run without the rule
				platform: "opencode",
				event_name: "PostToolUse",
				session_id: "session-1",
				tool_name: "Stop",
				findings: [],
				errors: null,
				output: null,
			},
			{
				timestamp: "2026-06-14T12:00:01.000Z", // last comparable run with the rule
				platform: "opencode",
				event_name: "PostToolUse",
				session_id: "session-2",
				tool_name: "Stop",
				findings: [{ rule_id: "PY-CODE-010", severity: "HIGH", decision: "warn", message: "fired" }],
				errors: null,
				output: null,
			},
			{
				timestamp: "2026-06-14T12:00:02.000Z", // unrelated later run without the rule
				platform: "opencode",
				event_name: "PostToolUse",
				session_id: "session-2",
				tool_name: "Bash",
				findings: [],
				errors: null,
				output: null,
			},
		];

		// Act
		const signals = computeCalibrationSignals(rules, results);

		// Assert
		const signal = signals.find((s) => s.rule_id === "PY-CODE-010");
		expect(signal).toBeDefined();
		// session-1: 1 delivered, 0 persistent
		// session-2: 1 delivered, 1 persistent
		// total: 2 delivered, 1 persistent -> 50% raw persistence with low volume/breadth scores below saturation.
		expect(signal?.decisionVariance).toBe(24);
		expect(signal?.deliveredSessions).toBe(2);
		expect(signal?.persistentDeliveredFindings).toBe(1);
		expect(signal?.isVariableSuspect).toBe(false);
	});

	it("caps persistence rate when later comparable results contain more findings", () => {
		// Arrange: persistence should mean the original delivered finding survived,
		// not that a later run with more findings can inflate one-session confidence.
		const rules = [
			{ ...createFinding("PY-CODE-010", "warn", "session-1"), timestamp: "2026-06-14T12:00:01.000Z" },
		];
		const results: HookResult[] = [
			{
				timestamp: "2026-06-14T12:00:01.000Z",
				platform: "opencode",
				event_name: "PostToolUse",
				session_id: "session-1",
				tool_name: "Stop",
				findings: [{ rule_id: "PY-CODE-010", severity: "HIGH", decision: "warn", message: "first" }],
				errors: null,
				output: null,
			},
			{
				timestamp: "2026-06-14T12:00:02.000Z",
				platform: "opencode",
				event_name: "PostToolUse",
				session_id: "session-1",
				tool_name: "Stop",
				findings: [
					{ rule_id: "PY-CODE-010", severity: "HIGH", decision: "warn", message: "later 1" },
					{ rule_id: "PY-CODE-010", severity: "HIGH", decision: "warn", message: "later 2" },
					{ rule_id: "PY-CODE-010", severity: "HIGH", decision: "warn", message: "later 3" },
				],
				errors: null,
				output: null,
			},
		];

		// Act
		const signals = computeCalibrationSignals(rules, results);

		// Assert
		const signal = signals.find((s) => s.rule_id === "PY-CODE-010");
		expect(signal?.decisionVariance).toBe(51);
		expect(signal?.isVariableSuspect).toBe(true);
	});
});
