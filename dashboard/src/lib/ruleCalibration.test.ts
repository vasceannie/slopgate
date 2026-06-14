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

	it("bounds and caps runtime error pressure to 100 for rules with errors", () => {
		// Arrange: 10 errors for PY-CODE-010, but only 1 finding
		const rules = [createFinding("PY-CODE-010", "block", "session-1")];
		const results: HookResult[] = Array.from({ length: 10 }, (_, i) => ({
			timestamp: "2026-06-14T12:00:01.000Z",
			platform: "opencode",
			event_name: "PostToolUse",
			session_id: `session-error-${i}`,
			tool_name: "Stop",
			findings: [],
			errors: ["PY-CODE-010: something crashed"],
			output: null,
		}));

		// Act
		const signals = computeCalibrationSignals(rules, results);

		// Assert
		const signal = signals.find(s => s.rule_id === "PY-CODE-010");
		expect(signal).toBeDefined();
		expect(signal?.runtimeErrorPressure).toBe(100); // capped at 100
		expect(signal?.isRuntimeErrorSuspect).toBe(true);
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
		expect(signal?.errorCount).toBe(0);
		expect(signal?.runtimeErrorPressure).toBe(0);
	});

	it("does not corrupt clean counts when overlapping signals are present", () => {
		// Arrange: rule with both high advisory pressure and variable decisions
		// It should be both isAdvisorySuspect and isVariableSuspect, and NOT isClean.
		const rules = [
			createFinding("PY-CODE-013", "allow", "session-1"),
			createFinding("PY-CODE-013", "block", "session-2"),
			createFinding("PY-CODE-013", "warn", "session-3"),
			createFinding("PY-CODE-013", "warn", "session-4"),
			createFinding("PY-CODE-013", "warn", "session-5"),
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

	it("correctly maps errors to lowercase CLI rules without duplicating them", () => {
		const rules = [createFinding("repeated-code-block", "block", "session-1")];
		const results: HookResult[] = [
			{
				timestamp: "2026-06-14T12:00:01.000Z",
				platform: "opencode",
				event_name: "PostToolUse",
				session_id: "session-1",
				tool_name: "Stop",
				findings: [],
				errors: ["REPEATED-CODE-BLOCK: some error text"],
				output: null,
			}
		];

		const signals = computeCalibrationSignals(rules, results);

		const signal = signals.find(s => s.rule_id === "repeated-code-block");
		expect(signal).toBeDefined();
		expect(signal?.errorCount).toBe(1);
		expect(signal?.runtimeErrorPressure).toBe(100);

		const dupSignal = signals.find(s => s.rule_id === "REPEATED-CODE-BLOCK");
		expect(dupSignal).toBeUndefined();
	});
});
