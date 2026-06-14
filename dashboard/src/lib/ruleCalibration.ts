import type { Severity, RuleFinding, HookResult, Decision } from "@/types/slopgate";
import { resolveDecision } from "@/hooks/useTraceData";

export type CalibrationMode = "advisory" | "error" | "variance";

export type CalibrationConfidence = "low" | "medium" | "high";

export interface RuleCalibrationSignal {
	rule_id: string;
	advisoryPressure: number;      // 0-100
	runtimeErrorPressure: number;  // 0-100
	decisionVariance: number;      // 0-100
	confidence: CalibrationConfidence;
	totalFindings: number;
	blockCount: number;
	warnCount: number;
	allowCount: number;
	allowAfterWarn: number;
	errorCount: number;
	severity: Severity;
	sessionsCount: number;
	isAdvisorySuspect: boolean;
	isRuntimeErrorSuspect: boolean;
	isVariableSuspect: boolean;
	isClean: boolean;
	recentExampleMessage?: string | null;
	recentExampleError?: string | null;
}

export function computeCalibrationSignals(
	rules: RuleFinding[],
	results: HookResult[],
): RuleCalibrationSignal[] {
	const byRule = new Map<string, RuleFinding[]>();
	const knownRuleIds = new Set<string>();
	const upperToOriginalRuleId = new Map<string, string>();

	for (const r of rules) {
		if (!byRule.has(r.rule_id)) byRule.set(r.rule_id, []);
		byRule.get(r.rule_id)?.push(r);
		knownRuleIds.add(r.rule_id);
		upperToOriginalRuleId.set(r.rule_id.toUpperCase(), r.rule_id);
	}

	for (const r of results) {
		for (const f of r.findings) {
			knownRuleIds.add(f.rule_id);
			upperToOriginalRuleId.set(f.rule_id.toUpperCase(), f.rule_id);
		}
	}
	const sessionFinalDecision = new Map<string, Decision>();
	for (const r of results) {
		const d = resolveDecision(r.findings);
		const existing = sessionFinalDecision.get(r.session_id);
		if (!existing || d === "block" || d === "deny") {
			sessionFinalDecision.set(r.session_id, d);
		}
	}

	const errorsByRule = new Map<string, number>();
	const parsedErrorSamples = new Map<string, string[]>();

	for (const r of results) {
		for (const err of r.errors ?? []) {
			const match = err.match(/^([A-Za-z0-9_-]+):\s*(.*)/s);
			let matchedRuleId: string | null = null;
			let cleanErrMsg = err;
			if (match) {
				const potentialId = match[1].toUpperCase();
				const originalId = upperToOriginalRuleId.get(potentialId);
				if (originalId) {
					matchedRuleId = originalId;
					cleanErrMsg = match[2];
				} else if (/^[A-Z0-9]+-[A-Z0-9_-]+$/.test(potentialId)) {
					const lower = potentialId.toLowerCase();
					let foundCaseInsensitive = false;
					for (const kid of knownRuleIds) {
						if (kid.toUpperCase() === potentialId) {
							matchedRuleId = kid;
							foundCaseInsensitive = true;
							break;
						}
					}
					if (!foundCaseInsensitive) {
						const isUppercasePrefix = /^(PY|BUILTIN|STOP|GLOBAL|LG|TS|FE|RS|GIT|SHELL|QA|WARN|CONFIG|STYLE|REMIND)-/i.test(potentialId);
						matchedRuleId = isUppercasePrefix ? potentialId : lower;
					}
					cleanErrMsg = match[2];
				}
			}
			if (matchedRuleId) {
				errorsByRule.set(matchedRuleId, (errorsByRule.get(matchedRuleId) || 0) + 1);
				let samples = parsedErrorSamples.get(matchedRuleId);
				if (!samples) {
					samples = [];
					parsedErrorSamples.set(matchedRuleId, samples);
				}
				if (samples.length < 5) {
					samples.push(cleanErrMsg);
				}
			}
		}
	}

	const signals: RuleCalibrationSignal[] = [];
	const allRuleIds = new Set<string>([...byRule.keys(), ...errorsByRule.keys()]);

	for (const rule_id of allRuleIds) {
		const findings = byRule.get(rule_id) || [];
		const totalFindings = findings.length;

		const decisions = findings.map((f) => f.decision ?? "context");
		const blockCount = decisions.filter(
			(d) => d === "block" || d === "deny",
		).length;
		const warnCount = decisions.filter(
			(d) => d === "warn" || d === "context" || d === "ask" || d === "info",
		).length;
		const allowCount = decisions.filter((d) => d === "allow").length;

		const sessionsWithRule = [...new Set(findings.map((f) => f.session_id))];
		const sessionsCount = sessionsWithRule.length;

		const allowAfterWarn = sessionsWithRule.filter((sid) => {
			const ruleDecisions = findings
				.filter((f) => f.session_id === sid)
				.map((f) => f.decision ?? "context");
			const hadWarning = ruleDecisions.some(
				(d) => d === "warn" || d === "ask" || d === "context" || d === "info",
			);
			const sessionDecision = sessionFinalDecision.get(sid);
			const sessionAllowed = sessionDecision !== "block" && sessionDecision !== "deny" && sessionDecision !== "ask";
			return hadWarning && sessionAllowed;
		}).length;

		// 1. advisoryPressure
		const warnRatio = totalFindings > 0 ? warnCount / totalFindings : 0;
		const allowAfterWarnRatio = sessionsCount > 0 ? allowAfterWarn / sessionsCount : 0;
		const sampleSizeConfidence = Math.min(sessionsCount / 5, 1.0);
		const advisoryPressure = Math.min(
			100,
			Math.round((allowAfterWarnRatio * 60 + warnRatio * 40) * sampleSizeConfidence),
		);

		// 2. runtimeErrorPressure
		const errorCount = errorsByRule.get(rule_id) || 0;
		let runtimeErrorPressure = 0;
		if (errorCount > 0) {
			if (totalFindings > 0) {
				runtimeErrorPressure = Math.min(
					100,
					Math.round((errorCount / totalFindings) * 100),
				);
			} else {
				runtimeErrorPressure = Math.min(100, errorCount * 20);
			}
		}

		// 3. decisionVariance
		let decisionVariance = 0;
		if (totalFindings > 0) {
			const p_allow = allowCount / totalFindings;
			const p_block = blockCount / totalFindings;
			const p_warn = warnCount / totalFindings;
			const varianceVal = 1 - (p_allow * p_allow + p_block * p_block + p_warn * p_warn);
			// Max varianceVal for 3 categories is 2/3 (when each is 1/3).
			// To normalize to 0-100, multiply by 150.
			const rawVariance = varianceVal * 150;
			const varianceSampleSizeFactor = sessionsCount >= 5 ? 1.0 : sessionsCount >= 3 ? 0.5 : 0.0;
			decisionVariance = Math.min(100, Math.round(rawVariance * varianceSampleSizeFactor));
		}

		// 4. confidence
		let confidence: CalibrationConfidence = "low";
		if (totalFindings > 0) {
			if (sessionsCount >= 8 && totalFindings >= 10) {
				confidence = "high";
			} else if (sessionsCount >= 3 && totalFindings >= 4) {
				confidence = "medium";
			}
		}

		// Suspect categories
		const isAdvisorySuspect = advisoryPressure > 30;
		const isRuntimeErrorSuspect = runtimeErrorPressure > 30;
		const isVariableSuspect = decisionVariance > 30;
		const isClean = !isAdvisorySuspect && !isRuntimeErrorSuspect && !isVariableSuspect;

		// severity fallback
		let severity: Severity = "MEDIUM";
		if (totalFindings > 0) {
			severity = findings[0].severity;
		} else {
			// fallback check from results
			let foundSeverity: Severity | null = null;
			for (const r of results) {
				const f = r.findings.find((x) => x.rule_id === rule_id);
				if (f) {
					foundSeverity = f.severity;
					break;
				}
			}
			if (foundSeverity) {
				severity = foundSeverity;
			}
		}

		const messageFinding = findings.find((f) => f.message);
		const recentExampleMessage = messageFinding ? messageFinding.message : null;

		const errorSamples = parsedErrorSamples.get(rule_id) || [];
		const recentExampleError = errorSamples.length > 0 ? errorSamples[0] : null;

		signals.push({
			rule_id,
			advisoryPressure,
			runtimeErrorPressure,
			decisionVariance,
			confidence,
			totalFindings,
			blockCount,
			warnCount,
			allowCount,
			allowAfterWarn,
			errorCount,
			severity,
			sessionsCount,
			isAdvisorySuspect,
			isRuntimeErrorSuspect,
			isVariableSuspect,
			isClean,
			recentExampleMessage,
			recentExampleError,
		});
	}

	return signals;
}
